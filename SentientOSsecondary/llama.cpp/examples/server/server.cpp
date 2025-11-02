#include "static_asset_manifest.hpp"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace llama::server {

namespace {
std::string to_lower(std::string_view value) {
    std::string lowered(value);
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return lowered;
}

std::string guess_content_type(const std::filesystem::path &path) {
    auto ext = to_lower(path.extension().string());
    if (ext == ".gz") {
        ext = to_lower(path.stem().extension().string());
    }

    if (ext == ".js" || ext == ".mjs") {
        return "application/javascript";
    }
    if (ext == ".css") {
        return "text/css";
    }
    if (ext == ".html") {
        return "text/html";
    }
    if (ext == ".json") {
        return "application/json";
    }
    if (ext == ".svg") {
        return "image/svg+xml";
    }
    if (ext == ".png") {
        return "image/png";
    }
    if (ext == ".jpg" || ext == ".jpeg") {
        return "image/jpeg";
    }
    if (ext == ".ico") {
        return "image/x-icon";
    }
    return "application/octet-stream";
}

bool contains_traversal(std::string_view request) {
    if (request.find("\\") != std::string_view::npos) {
        return true;
    }
    std::string_view token = "..";
    auto pos = request.find(token);
    while (pos != std::string_view::npos) {
        bool before = pos == 0 || request[pos - 1] == '/' || request[pos - 1] == '\\';
        auto after_index = pos + token.size();
        bool after = after_index >= request.size() || request[after_index] == '/' || request[after_index] == '\\';
        if (before && after) {
            return true;
        }
        pos = request.find(token, pos + 1);
    }
    return false;
}

std::vector<std::string> expand_aliases(const std::string &path) {
    std::vector<std::size_t> toggles;
    for (std::size_t i = 0; i < path.size(); ++i) {
        if (path[i] == '-' || path[i] == '_') {
            toggles.push_back(i);
        }
    }

    if (toggles.empty()) {
        return {path};
    }

    std::vector<std::string> results;
    const std::size_t combinations = static_cast<std::size_t>(1) << toggles.size();
    results.reserve(combinations);

    for (std::size_t mask = 0; mask < combinations; ++mask) {
        std::string candidate = path;
        for (std::size_t bit = 0; bit < toggles.size(); ++bit) {
            const std::size_t index = toggles[bit];
            if ((mask & (static_cast<std::size_t>(1) << bit)) != 0U) {
                candidate[index] = '-';
            } else {
                candidate[index] = '_';
            }
        }
        results.push_back(std::move(candidate));
    }

    results.push_back(path);
    std::sort(results.begin(), results.end());
    results.erase(std::unique(results.begin(), results.end()), results.end());
    return results;
}

std::string canonical_alias(std::string_view path) {
    std::string canonical(path);
    for (char &ch : canonical) {
        if (ch == '-') {
            ch = '_';
        }
    }
    return canonical;
}

std::vector<unsigned char> load_file_bytes(const std::filesystem::path &path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error("Failed to open asset: " + path.string());
    }
    return std::vector<unsigned char>(std::istreambuf_iterator<char>(stream), {});
}

}  // namespace

class StaticAssetResolver {
public:
    struct ResolvedAsset {
        std::string route;
        std::string content_type;
        std::string encoding;
        std::vector<unsigned char> body;
        bool immutable_cache;
    };

    using Manifest = std::span<const EmbeddedAsset>;

    StaticAssetResolver(std::filesystem::path web_root, Manifest embedded_assets)
        : web_root_(std::move(web_root)) {
        for (const auto &asset : embedded_assets) {
            manifest_.emplace(canonical_alias(asset.route), &asset);
        }
    }

    std::optional<ResolvedAsset> Resolve(std::string_view request_path) const {
        const std::string sanitized = sanitize(request_path);
        if (sanitized.empty()) {
            return std::nullopt;
        }

        if (auto embedded = resolve_embedded(sanitized)) {
            return embedded;
        }

        if (auto filesystem_asset = resolve_filesystem(sanitized)) {
            return filesystem_asset;
        }

        return std::nullopt;
    }

    ResolvedAsset resolve_or_throw(std::string_view request_path) const {
        auto asset = Resolve(request_path);
        if (!asset) {
            throw std::runtime_error("Static asset not found: " + std::string(request_path));
        }
        return *asset;
    }

private:
    static std::string sanitize(std::string_view request_path) {
        if (request_path.empty()) {
            return "/";
        }

        auto trimmed = request_path;
        auto query_pos = trimmed.find('?');
        if (query_pos != std::string_view::npos) {
            trimmed = trimmed.substr(0, query_pos);
        }
        auto fragment_pos = trimmed.find('#');
        if (fragment_pos != std::string_view::npos) {
            trimmed = trimmed.substr(0, fragment_pos);
        }

        std::string normalized(trimmed);
        if (normalized.empty()) {
            normalized = "/";
        } else if (normalized.front() != '/') {
            normalized.insert(normalized.begin(), '/');
        }

        if (contains_traversal(normalized)) {
            return {};
        }

        return normalized;
    }

    std::optional<ResolvedAsset> resolve_embedded(const std::string &request) const {
        const auto canonical = canonical_alias(request);
        const auto it = manifest_.find(canonical);
        if (it == manifest_.end()) {
            return std::nullopt;
        }

        const auto &asset = *it->second;
        ResolvedAsset resolved;
        resolved.route = std::string(asset.route);
        resolved.content_type = std::string(asset.content_type);
        if (asset.gzip_encoded) {
            resolved.encoding = "gzip";
        }
        resolved.body.assign(asset.data, asset.data + asset.size);
        resolved.immutable_cache = true;
        return resolved;
    }

    std::optional<ResolvedAsset> resolve_filesystem(const std::string &request) const {
        if (web_root_.empty()) {
            return std::nullopt;
        }

        for (const auto &alias : expand_aliases(request)) {
            if (alias.empty() || alias.front() != '/') {
                continue;
            }
            std::filesystem::path relative(alias.substr(1));
            auto candidate = web_root_ / relative;
            if (!std::filesystem::exists(candidate) || !std::filesystem::is_regular_file(candidate)) {
                continue;
            }

            ResolvedAsset resolved;
            resolved.route = alias;
            resolved.content_type = guess_content_type(candidate);
            if (candidate.extension() == ".gz") {
                resolved.encoding = "gzip";
            }
            resolved.body = load_file_bytes(candidate);
            resolved.immutable_cache = false;
            return resolved;
        }

        return std::nullopt;
    }

    std::filesystem::path web_root_;
    std::unordered_map<std::string, const EmbeddedAsset *> manifest_;
};

}  // namespace llama::server

int main() {
    using llama::server::StaticAssetResolver;
    StaticAssetResolver resolver(std::filesystem::path{"public"}, EmbeddedAssetManifest());
    auto asset = resolver.Resolve("/assets/index.js");
    if (!asset) {
        return 1;
    }
    return 0;
}
