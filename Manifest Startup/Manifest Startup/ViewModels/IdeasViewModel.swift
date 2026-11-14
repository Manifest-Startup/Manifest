import Foundation
import SwiftUI
import Combine

@MainActor
class IdeasViewModel: ObservableObject {
    
    @Published var ideas: [Idea] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var selectedIdea: Idea?
    
    private let apiService = APIService.shared
    
    func loadIdeas() async {
        isLoading = true
        errorMessage = nil
        
        do {
            ideas = try await apiService.getIdeas()
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }
    
    func createIdea(title: String) async {
        do {
            let newIdea = try await apiService.createIdea(title: title)
            ideas.insert(newIdea, at: 0)
            selectedIdea = newIdea
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    
    func togglePublish(idea: Idea) async {
        do {
            let result = try await apiService.togglePublishIdea(id: idea.id)
            if let index = ideas.firstIndex(where: { $0.id == idea.id }) {
                let updatedIdea = Idea(
                    id: idea.id,
                    title: idea.title,
                    description: idea.description,
                    isPublished: result.isPublished,
                    pitchDeck: idea.pitchDeck,
                    businessModelCanvas: idea.businessModelCanvas,
                    createdAt: idea.createdAt,
                    updatedAt: idea.updatedAt
                )
                ideas[index] = updatedIdea
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    
    func deleteIdea(idea: Idea) {
        ideas.removeAll { $0.id == idea.id }
    }
}
