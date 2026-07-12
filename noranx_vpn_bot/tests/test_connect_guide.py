from bot.services.connect_guide import APPS, PLATFORM_APPS, format_app_guide


def test_all_platform_apps_exist():
    for platform, app_ids in PLATFORM_APPS.items():
        for app_id in app_ids:
            assert app_id in APPS, f"{app_id} missing for {platform}"


def test_five_apps():
    expected = {"v2rayng", "v2rayn", "v2box", "happ", "v2raytun"}
    assert expected == set(APPS.keys())


def test_format_app_guide_has_steps():
    text = format_app_guide("v2rayng")
    assert "V2RayNG" in text
    assert "1." in text
