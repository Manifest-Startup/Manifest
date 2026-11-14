import Foundation

struct Investment: Identifiable, Codable {
    let id: String
    let ideaId: String
    let ideaTitle: String
    let ideaDescription: String?
    let cashAmount: Double
    let sweatEquityValue: Double
    let equityPercentage: Double
    let status: InvestmentStatus
    let createdAt: Date?
    
    enum CodingKeys: String, CodingKey {
        case id = "investmentId"
        case ideaId
        case ideaTitle
        case ideaDescription
        case cashAmount
        case sweatEquityValue
        case equityPercentage
        case status
        case createdAt
    }
    
    var totalValue: Double {
        cashAmount + sweatEquityValue
    }
}

enum InvestmentStatus: String, Codable {
    case pending
    case confirmed
    case cancelled
    
    var displayColor: String {
        switch self {
        case .pending: return "yellow"
        case .confirmed: return "green"
        case .cancelled: return "red"
        }
    }
}

struct PortfolioStats {
    let totalInvestments: Int
    let totalValue: Double
    let totalEquity: Double
    
    static var empty: PortfolioStats {
        PortfolioStats(totalInvestments: 0, totalValue: 0, totalEquity: 0)
    }
}
