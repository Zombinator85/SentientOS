cmake_minimum_required(VERSION 3.21)

project(sentientos_llama_server LANGUAGES CXX)
set(PROJECT_VERSION "1.0.0-rc1")

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(LLAMA_SERVER_PUBLIC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/public)
file(GLOB_RECURSE LLAMA_SERVER_PUBLIC_ASSETS
     RELATIVE ${LLAMA_SERVER_PUBLIC_DIR}
     ${LLAMA_SERVER_PUBLIC_DIR}/*)

set(LLAMA_SERVER_EMBED_HEADERS)
set(LLAMA_SERVER_EMBED_RECORDS)

foreach(asset ${LLAMA_SERVER_PUBLIC_ASSETS})
    set(source ${LLAMA_SERVER_PUBLIC_DIR}/${asset})
    string(REPLACE "." "_" symbol ${asset})
    string(REPLACE "/" "_" symbol ${symbol})
    string(REPLACE "-" "_" symbol ${symbol})
    string(REPLACE " " "_" symbol ${symbol})
    string(TOLOWER ${symbol} symbol)
    set(output ${CMAKE_CURRENT_BINARY_DIR}/${symbol}.hpp)

    add_custom_command(
        OUTPUT ${output}
        COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}
        COMMAND ${CMAKE_COMMAND}
            -DASSET=${source}
            -DSYMBOL=${symbol}
            -DOUTPUT=${output}
            -P ${CMAKE_CURRENT_SOURCE_DIR}/embed_asset.cmake
        DEPENDS ${source} ${CMAKE_CURRENT_SOURCE_DIR}/embed_asset.cmake
        COMMENT "Embedding asset ${asset}"
        VERBATIM
    )

    list(APPEND LLAMA_SERVER_EMBED_HEADERS ${output})
    list(APPEND LLAMA_SERVER_EMBED_RECORDS "${asset}|${symbol}|${output}")
endforeach()

set(LLAMA_SERVER_MANIFEST ${CMAKE_CURRENT_BINARY_DIR}/static_asset_manifest.hpp)
set(LLAMA_SERVER_RECORD_FILE ${CMAKE_CURRENT_BINARY_DIR}/embedded_assets.txt)
file(WRITE ${LLAMA_SERVER_RECORD_FILE} "")
foreach(record ${LLAMA_SERVER_EMBED_RECORDS})
    file(APPEND ${LLAMA_SERVER_RECORD_FILE} "${record}\n")
endforeach()

add_custom_command(
    OUTPUT ${LLAMA_SERVER_MANIFEST}
    COMMAND ${CMAKE_COMMAND}
        -DOUTPUT=${LLAMA_SERVER_MANIFEST}
        -DRECORD_FILE=${LLAMA_SERVER_RECORD_FILE}
        -P ${CMAKE_CURRENT_SOURCE_DIR}/generate_static_asset_manifest.cmake
    DEPENDS ${LLAMA_SERVER_EMBED_HEADERS} ${LLAMA_SERVER_RECORD_FILE}
    COMMENT "Generating embedded asset manifest"
    VERBATIM
)

add_custom_target(server_embed
    DEPENDS ${LLAMA_SERVER_EMBED_HEADERS} ${LLAMA_SERVER_MANIFEST})

add_executable(llama-server
    server.cpp)

target_include_directories(llama-server
    PRIVATE
        ${CMAKE_CURRENT_BINARY_DIR}
)

target_sources(llama-server
    PRIVATE ${LLAMA_SERVER_MANIFEST})

add_dependencies(llama-server server_embed)
