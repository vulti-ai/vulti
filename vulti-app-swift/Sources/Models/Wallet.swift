import Foundation

// Credit card data stored in ~/.vulti/agents/{id}/creditcard.json
// Vault data is ONLY in .vult keyshare files — never in JSON metadata.
struct CreditCardFile: Codable {
    var creditCard: CreditCardEntry?

    enum CodingKeys: String, CodingKey {
        case creditCard = "credit_card"
    }
}

struct CreditCardEntry: Codable {
    var name: String?
    var number: String?
    var expiry: String?
    var code: String?
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
