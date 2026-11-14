import Foundation
import SwiftUI
import Combine

@MainActor
class AccountViewModel: ObservableObject {
    
    @Published var user: User?
    @Published var investments: [Investment] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var isSaving = false
    
    @Published var firstName: String = ""
    @Published var lastName: String = ""
    @Published var email: String = ""
    @Published var bio: String = ""
    
    private let apiService = APIService.shared
    
    var portfolioStats: PortfolioStats {
        let totalValue = investments.reduce(0) { $0 + $1.totalValue }
        let totalEquity = investments.reduce(0) { $0 + $1.equityPercentage }
        return PortfolioStats(
            totalInvestments: investments.count,
            totalValue: totalValue,
            totalEquity: totalEquity
        )
    }
    
    func loadAccount() async {
        isLoading = true
        errorMessage = nil
        
        do {
            async let userTask = apiService.getAccount()
            async let portfolioTask = apiService.getPortfolio()
            
            let (loadedUser, loadedInvestments) = try await (userTask, portfolioTask)
            
            user = loadedUser
            investments = loadedInvestments
            
            firstName = loadedUser.firstName ?? ""
            lastName = loadedUser.lastName ?? ""
            email = loadedUser.email
            bio = loadedUser.bio ?? ""
            
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func saveChanges() async {
        isSaving = true
        
        do {
            let input = UpdateAccountInput(
                firstName: firstName.isEmpty ? nil : firstName,
                lastName: lastName.isEmpty ? nil : lastName,
                email: email.isEmpty ? nil : email,
                bio: bio.isEmpty ? nil : bio
            )
            
            user = try await apiService.updateAccount(input: input)
            isSaving = false
        } catch {
            errorMessage = error.localizedDescription
            isSaving = false
        }
    }
}

