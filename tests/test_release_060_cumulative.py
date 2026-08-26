from aae_observability.testing import MockLangChainAgent, MockMicrosoftAgent, MockMultiAgentWorkflow


def test_framework_shaped_mocks_are_cumulative():
    maf = MockMicrosoftAgent()
    chain = MockLangChainAgent()
    workflow = MockMultiAgentWorkflow()
    assert maf.run("x", correlation_id="m")["correlation_id"] == "m"
    assert chain.invoke("x", correlation_id="l")["correlation_id"] == "l"
    assert workflow.handoff("planner", "reviewer", correlation_id="c")["target"] == "reviewer"
