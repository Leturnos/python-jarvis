from core.infra.config import load_config


def test_config_ram_optimization_defaults():
    cfg = load_config()
    stt_cfg = cfg.get("stt", {})
    runtime_cfg = cfg.get("runtime", {})
    mem_mon = runtime_cfg.get("memory_monitor", {})
    mem_opt = runtime_cfg.get("memory_optimization", {})

    assert stt_cfg.get("lazy_load") is True
    assert stt_cfg.get("auto_unload_seconds") == 180
    assert mem_mon.get("enable_working_set_trim") is True
    assert mem_opt.get("lazy_load_secondary_modules") is True
    assert mem_opt.get("unload_wakeword_on_suspend") is True
