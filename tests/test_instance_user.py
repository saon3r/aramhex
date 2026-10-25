"""单实例用户名：环境变量缺失时不能崩，而且不能把 run() 的正文裁掉。"""

import inspect


def test_single_instance_user_falls_back_without_environment(monkeypatch):
    """剥掉 USERNAME 的环境里（计划任务/服务式启动）不能因为 getpass 直接崩。"""
    import getpass

    from lolhex.ui import overlay

    def boom():
        raise OSError("No username set in the environment")

    monkeypatch.setattr(getpass, "getuser", boom)
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert overlay._instance_user() == "default"
    monkeypatch.setenv("USERNAME", "asaon")
    assert overlay._instance_user() == "asaon"

def test_run_is_still_a_whole_function():
    """曾经把辅助函数插在 run() 中间，模块级 def 直接把 run() 的正文截断：
    界面「瞬间退出、只写一行启动日志」。这里钉住 run() 的骨架。"""
    from lolhex.ui import overlay

    source = inspect.getsource(overlay.run)
    assert "notify_running" in source
    assert "engine = make_engine()" in source
    assert "app.exec()" in source                       # 真的进事件循环，不是提前返回
