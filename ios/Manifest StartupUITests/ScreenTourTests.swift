import XCTest

/// Walks every main screen in demo mode and attaches a screenshot of each, for
/// design and accessibility review. Set `TOUR_DIR` to also write PNGs to disk.
final class ScreenTourTests: XCTestCase {
    private var app: XCUIApplication!
    private var step = 0

    override func setUpWithError() throws {
        continueAfterFailure = true
        app = XCUIApplication()
        app.launchArguments = ["-demo"] + (ProcessInfo.processInfo.environment["TOUR_DARK"] == "1" ? ["-AppleInterfaceStyle", "Dark"] : [])
        app.launch()
    }

    @MainActor
    func testTour() throws {
        XCTAssertTrue(app.staticTexts["Clinic Copilot"].firstMatch.waitForExistence(timeout: 10))
        snap("ideas")

        app.staticTexts["Clinic Copilot"].firstMatch.tap()
        sleep(2)
        snap("idea-detail")
        app.swipeUp()
        snap("idea-detail-2")

        app.staticTexts["Pitch Deck"].firstMatch.tap()
        sleep(2)
        snap("document")
        app.navigationBars.buttons.element(boundBy: 0).tap()

        app.staticTexts["Business Model Canvas"].firstMatch.tap()
        sleep(2)
        snap("canvas")
        app.navigationBars.buttons.element(boundBy: 0).tap()

        app.staticTexts["Cap table & investments"].firstMatch.tap()
        sleep(2)
        snap("cap-table")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()

        app.buttons["newIdea"].tap()
        sleep(1)
        snap("new-idea")
        app.buttons["Cancel"].tap()

        app.tabBars.buttons["Shorts"].tap()
        sleep(3)
        snap("shorts")

        app.tabBars.buttons["Inbox"].tap()
        sleep(2)
        snap("inbox")
        app.staticTexts["Sam Okafor"].firstMatch.tap()
        sleep(2)
        snap("thread")
        app.navigationBars.buttons.element(boundBy: 0).tap()

        app.tabBars.buttons["Portfolio"].tap()
        sleep(2)
        snap("portfolio")

        app.buttons["account"].firstMatch.tap()
        sleep(2)
        snap("account")
        app.buttons["Done"].tap()

        app.tabBars.buttons["Search"].tap()
        sleep(1)
        let field = app.searchFields.firstMatch
        if field.waitForExistence(timeout: 3) {
            field.tap()
            field.typeText("clinic")
            sleep(2)
        }
        snap("search")
    }

    private func snap(_ name: String) {
        step += 1
        let shot = app.screenshot()
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = String(format: "%02d-%@", step, name)
        attachment.lifetime = .keepAlways
        add(attachment)
        if let dir = ProcessInfo.processInfo.environment["TOUR_DIR"] {
            let url = URL(fileURLWithPath: dir).appendingPathComponent(String(format: "%02d-%@.png", step, name))
            try? shot.pngRepresentation.write(to: url)
        }
    }
}
