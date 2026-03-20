import Foundation

// Matches ~/.vulti/agents/{id}/wallet.json
struct WalletFile: Codable {
    var creditCard: CreditCardEntry?
    var crypto: CryptoWalletEntry?

    enum CodingKeys: String, CodingKey {
        case creditCard = "credit_card"
        case crypto
    }
}

struct CreditCardEntry: Codable {
    var name: String?
    var number: String?
    var expiry: String?
    var code: String?
}

struct CryptoWalletEntry: Codable {
    var vaultId: String?
    var name: String?
    var email: String?

    enum CodingKeys: String, CodingKey {
        case vaultId = "vault_id"
        case name, email
    }
}

struct VaultInfo {
    let name: String
    let vaultId: String
    let filePath: String
}

struct VaultCreateResult: Codable {
    var vaultId: String?
    var vault_id: String?
    var id: String?
    var data: VaultCreateData?

    struct VaultCreateData: Codable {
        var vaultId: String?
        var vault_id: String?
    }

    var resolvedId: String? {
        vaultId ?? vault_id ?? id ?? data?.vaultId ?? data?.vault_id
    }
}
