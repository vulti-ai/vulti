// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "VultiHub",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift.git", from: "7.0.0"),
        .package(url: "https://github.com/jpsim/Yams.git", from: "5.1.0"),
    ],
    targets: [
        .executableTarget(
            name: "VultiHub",
            dependencies: [
                .product(name: "GRDB", package: "GRDB.swift"),
                "Yams",
            ],
            path: "Sources",
            resources: [
                .copy("../Resources"),
            ]
        ),
    ]
)
