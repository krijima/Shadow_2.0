"""Drive actual header pointer input across iframe and viewport boundaries."""
from test_demo_panel_navigation import loaded_extension, panel


def test_panel_drag_is_bounded_and_stops_after_release(loaded_extension):
    page, worker, events = loaded_extension
    page.wait_for_timeout(700)
    header = panel(page).locator('#dragHeader').bounding_box()
    page.mouse.move(header['x'] + 70, header['y'] + 20)
    page.mouse.down()
    page.mouse.move(2, 2, steps=15)
    page.mouse.up()
    page.wait_for_timeout(300)
    frame = page.locator('#shadow-assistant-frame').bounding_box()
    assert frame['x'] >= 0 and frame['y'] >= 0
    page.mouse.move(900, 600, steps=6)
    page.wait_for_timeout(200)
    assert page.locator('#shadow-assistant-frame').bounding_box() == frame
    page.set_viewport_size({'width': 600, 'height': 450})
    page.wait_for_timeout(400)
    frame = page.locator('#shadow-assistant-frame').bounding_box()
    assert frame['x'] >= 0 and frame['y'] >= 0
    assert frame['x'] + frame['width'] <= 600
    assert frame['y'] + frame['height'] <= 450


def test_minimized_sphere_reopens_light_panel_without_losing_input(loaded_extension, tmp_path):
    page, worker, events = loaded_extension
    ui = panel(page)
    ui.locator('#instructionInput').fill('Keep this objective')
    ui.locator('#minimizeBtn').click()
    page.wait_for_timeout(400)
    frame = page.locator('#shadow-assistant-frame').bounding_box()
    assert frame['width'] <= 72 and frame['height'] <= 72
    page.screenshot(path=str(tmp_path / 'sphere.png'))
    ui.locator('#launcherBtn').click()
    page.wait_for_timeout(400)
    frame = page.locator('#shadow-assistant-frame').bounding_box()
    assert frame['width'] >= 400 and frame['height'] >= 500
    assert ui.locator('#instructionInput').input_value() == 'Keep this objective'
    colors = ui.locator('#app').evaluate('(node) => ({bg:getComputedStyle(node).backgroundColor, color:getComputedStyle(node).color})')
    assert colors['bg'] == 'rgb(248, 250, 252)'
    assert colors['color'] == 'rgb(23, 32, 51)'
    ui.locator('#minimizeBtn').click()
    page.wait_for_timeout(200)
    page.evaluate("() => shadowTestPopupMessage({type:'FOCUS_ASSISTANT'})")
    page.wait_for_timeout(300)
    assert page.locator('#shadow-assistant-frame').bounding_box()['width'] >= 400
    page.screenshot(path=str(tmp_path / 'light-panel.png'))
    print(f'UI screenshots: {tmp_path}')
