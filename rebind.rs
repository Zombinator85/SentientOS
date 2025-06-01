use std::{collections::HashMap, env, time::Duration};

use dotenv::dotenv;
use hyper::{body::to_bytes, Body, Client, Method, Request};
use hyper::client::HttpConnector;
use hyper_tls::HttpsConnector;
use serde_json::Value;
use tokio::time::sleep;

static PORT_TO_NAME: &[(&str, &str)] = &[
    ("9977", "gpt4o"),
    ("9988", "mixtral"),
    ("9966", "deepseek"),
];

static NGROK_APIS: &[(&str, &str)] = &[
    ("main", "http://localhost:4040/api/tunnels"),
    ("alt", "http://localhost:4041/api/tunnels"),
];

async fn get_public_urls(client: &Client<HttpsConnector<HttpConnector>>) -> HashMap<String, String> {
    let mut urls = HashMap::new();
    for (label, api) in NGROK_APIS {
        match api.parse::<hyper::Uri>() {
            Ok(uri) => match client.get(uri).await {
                Ok(mut res) if res.status().is_success() => {
                    if let Ok(bytes) = to_bytes(res.body_mut()).await {
                        if let Ok(v) = serde_json::from_slice::<Value>(&bytes) {
                            if let Some(tunnels) = v.get("tunnels").and_then(|t| t.as_array()) {
                                for t in tunnels {
                                    if let (Some(public_url), Some(addr)) = (
                                        t.get("public_url").and_then(|u| u.as_str()),
                                        t.get("config").and_then(|c| c.get("addr")).and_then(|a| a.as_str()),
                                    ) {
                                        if let Some(port) = addr.split(':').last() {
                                            if let Some((_, name)) = PORT_TO_NAME.iter().find(|(p, _)| *p == port) {
                                                urls.insert((*name).to_string(), public_url.to_string());
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Ok(res) => {
                    eprintln!("[{}] request failed: {}", label, res.status());
                }
                Err(err) => {
                    eprintln!("[{}] \u{1f4a5} {}", label, err);
                }
            },
            Err(err) => eprintln!("Invalid URI {}: {}", api, err),
        }
    }
    urls
}

async fn bind_webhook(
    client: &Client<HttpsConnector<HttpConnector>>,
    bot_name: &str,
    url: &str,
    tg_secret: &str,
) {
    let token_var = format!("BOT_TOKEN_{}", bot_name.to_ascii_uppercase());
    let token = match env::var(&token_var) {
        Ok(t) if !t.is_empty() => t,
        _ => {
            eprintln!("[❌] No token for {}", bot_name);
            return;
        }
    };

    let webhook_url = format!("{}/webhook", url);
    let endpoint = format!("https://api.telegram.org/bot{}/setWebhook", token);
    let payload = serde_json::json!({
        "url": webhook_url,
        "secret_token": tg_secret,
    });

    let req = Request::builder()
        .method(Method::POST)
        .uri(endpoint)
        .header("Content-Type", "application/json")
        .body(Body::from(serde_json::to_vec(&payload).unwrap()))
        .unwrap();

    match client.request(req).await {
        Ok(mut res) if res.status().is_success() => {
            println!("[✅] Bound {} to {}", bot_name, webhook_url);
        }
        Ok(mut res) => {
            let text = to_bytes(res.body_mut()).await.ok().map(|b| String::from_utf8_lossy(&b).into_owned()).unwrap_or_default();
            eprintln!("[❌] Failed {}: {}", bot_name, text);
        }
        Err(err) => {
            eprintln!("[{}] \u{1f4a5} {}", bot_name, err);
        }
    }
}

#[tokio::main]
async fn main() {
    dotenv().ok();
    let tg_secret = env::var("TG_SECRET").expect("TG_SECRET not set");

    println!("[🔄] Rebinding all Telegram webhooks...");
    sleep(Duration::from_secs(2)).await;

    let https = HttpsConnector::new();
    let client: Client<_, Body> = Client::builder().build(https);

    let urls = get_public_urls(&client).await;
    for (name, url) in urls {
        bind_webhook(&client, &name, &url, &tg_secret).await;
    }
}

