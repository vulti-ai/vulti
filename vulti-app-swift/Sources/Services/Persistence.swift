import Foundation

/// UserDefaults-backed persistence (matches localStorage keys from original).
enum Persistence {
    private static let defaults = UserDefaults.standard

    // vulti_token
    static var token: String? {
        get { defaults.string(forKey: "vulti_token") }
        set { defaults.set(newValue, forKey: "vulti_token") }
    }

    // vulti_active_agent
    static var activeAgentId: String? {
        get { defaults.string(forKey: "vulti_active_agent") }
        set { defaults.set(newValue, forKey: "vulti_active_agent") }
    }

    // vulti_settings
    static var settings: [String: Any] {
        get { defaults.dictionary(forKey: "vulti_settings") ?? [:] }
        set { defaults.set(newValue, forKey: "vulti_settings") }
    }

    // vulti-theme
    static var theme: String {
        get { defaults.string(forKey: "vulti-theme") ?? "dark" }
        set { defaults.set(newValue, forKey: "vulti-theme") }
    }

    // vulti_onboarding_complete
    static var onboardingComplete: Bool {
        get { defaults.bool(forKey: "vulti_onboarding_complete") }
        set { defaults.set(newValue, forKey: "vulti_onboarding_complete") }
    }
}
