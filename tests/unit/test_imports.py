def test_engineering_packages_import() -> None:
    import agentbox_core
    import agentbox_protocol
    import agentbox_runtime

    assert agentbox_core.__version__
    assert agentbox_protocol.MetaResponse(version=agentbox_core.__version__).api_version == "v1"
    assert agentbox_runtime.RuntimeAdapter is not None
