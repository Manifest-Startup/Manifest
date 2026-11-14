import Foundation
import SwiftUI
import Combine

class AuthService: ObservableObject {
    static let shared = AuthService()
    
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    @Published var isLoading = false
    @Published var errorMessage: String?
    
    private let tokenKey = "auth_token"
    private let apiService = APIService.shared
    
    init() {
        checkAuthStatus()
    }
    
    private func checkAuthStatus() {
        if let token = UserDefaults.standard.string(forKey: tokenKey) {
            apiService.setAuthToken(token)
            isAuthenticated = true
            loadCurrentUser()
        }
    }
    
    func login(email: String, password: String) async {
        await MainActor.run {
            isLoading = true
            errorMessage = nil
        }
        
        do {
            await MainActor.run {
                UserDefaults.standard.set("mock_token", forKey: tokenKey)
                apiService.setAuthToken("mock_token")
                isAuthenticated = true
                isLoading = false
            }
            loadCurrentUser()
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }
    
    func logout() {
        UserDefaults.standard.removeObject(forKey: tokenKey)
        apiService.setAuthToken(nil)
        isAuthenticated = false
        currentUser = nil
    }
    
    private func loadCurrentUser() {
        Task {
            do {
                let user = try await apiService.getAccount()
                await MainActor.run {
                    currentUser = user
                }
            } catch {
                print("Failed to load user: \(error)")
            }
        }
    }
}
