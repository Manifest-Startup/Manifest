//
//  ContentView.swift
//  Manifest Startup
//
//  Created by Mihir Kavishwar on 12/25/25.
//

import SwiftUI
import Combine

struct ContentView: View {
    @StateObject private var authService = AuthService.shared
    
    var body: some View {
        Group {
            if authService.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .environmentObject(authService)
    }
}

struct LoginView: View {
    @EnvironmentObject var authService: AuthService
    @State private var email = ""
    @State private var password = ""
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 32) {
                VStack(spacing: 8) {
                    Image(systemName: "lightbulb.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(.blue)
                    
                    Text("Manifest")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    
                    Text("Build your startup")
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 60)
                
                VStack(spacing: 16) {
                    TextField("Email", text: $email)
                        .textFieldStyle(.roundedBorder)
#if os(iOS)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
#endif
#if os(macOS)
                        .textContentType(.emailAddress)
#endif
                    
                    SecureField("Password", text: $password)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.password)
                    
                    Button {
                        Task {
                            await authService.login(email: email, password: password)
                        }
                    } label: {
                        if authService.isLoading {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("Sign In")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(email.isEmpty || password.isEmpty || authService.isLoading)
                    
                    if let error = authService.errorMessage {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }
                .padding(.horizontal, 32)
                
                Spacer()
                
                VStack(spacing: 16) {
                    Text("Don't have an account?")
                        .foregroundStyle(.secondary)
                    
                    Button("Create Account") {
                    }
                    .buttonStyle(.bordered)
                }
                .padding(.bottom, 32)
            }
        }
    }
}

#Preview {
    ContentView()
}

