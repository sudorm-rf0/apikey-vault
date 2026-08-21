// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "apikey-vault",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "apikey-vault", targets: ["APIVaultApp"]),
        .executable(name: "apikey-vault-selftest", targets: ["SelfTest"]),
    ],
    targets: [
        .target(name: "APIVaultCore"),
        .executableTarget(
            name: "APIVaultApp",
            dependencies: ["APIVaultCore"]
        ),
        .executableTarget(
            name: "SelfTest",
            dependencies: ["APIVaultCore"]
        ),
    ]
)
