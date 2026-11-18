import XCTest

/// Journeys against the synthetic `-demo` fixtures (no network, no accounts).
final class Manifest_StartupUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-demo"]
        app.launch()
    }

    @MainActor
    func testIdeasListOpensDetailAndDocument() throws {
        let idea = app.staticTexts["Clinic Copilot"].firstMatch
        XCTAssertTrue(idea.waitForExistence(timeout: 10))
        idea.tap()

        XCTAssertTrue(app.buttons["publish"].waitForExistence(timeout: 5))
        let deck = app.staticTexts["Pitch Deck"].firstMatch
        XCTAssertTrue(deck.waitForExistence(timeout: 5))
        deck.tap()
        XCTAssertTrue(app.staticTexts["Problem"].waitForExistence(timeout: 5))
    }

    @MainActor
    func testComposerRequiresText() throws {
        let newIdea = app.buttons["newIdea"]
        XCTAssertTrue(newIdea.waitForExistence(timeout: 10))
        newIdea.tap()
        let create = app.buttons["createIdea"]
        XCTAssertTrue(create.waitForExistence(timeout: 5))
        XCTAssertFalse(create.isEnabled)
        app.textFields["ideaTitle"].typeText("Solar kiosks")
        XCTAssertTrue(create.isEnabled)
    }

    @MainActor
    func testTabsAndAccount() throws {
        XCTAssertTrue(app.tabBars.buttons["Inbox"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Inbox"].tap()
        XCTAssertTrue(app.staticTexts["Sam Okafor"].waitForExistence(timeout: 5))

        app.tabBars.buttons["Portfolio"].tap()
        XCTAssertTrue(app.staticTexts["Rural telehealth kiosks"].waitForExistence(timeout: 5))

        app.buttons["account"].firstMatch.tap()
        XCTAssertTrue(app.buttons["signOut"].waitForExistence(timeout: 5))
    }

    @MainActor
    func testLaunchPerformance() throws {
        measure(metrics: [XCTApplicationLaunchMetric()]) {
            XCUIApplication().launch()
        }
    }
}
