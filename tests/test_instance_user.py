"""单实例用户名：环境变量缺失时不能崩。"""


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
