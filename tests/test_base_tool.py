"""
Unit tests for base tool interface.
"""

import pytest
from pydantic import BaseModel, Field
from eva_mcp.tools.base import BaseTool


class TestToolInput(BaseModel):
    """Test input schema."""
    param1: str = Field(description="Test parameter")
    param2: int = Field(default=10, description="Optional parameter")


class TestToolOutput(BaseModel):
    """Test output schema."""
    result: str


class ConcreteTestTool(BaseTool):
    """Concrete implementation of BaseTool for testing."""
    
    name = "test_tool"
    description = "Test tool implementation"
    input_schema = TestToolInput
    output_schema = TestToolOutput
    required_roles = ["test_role"]
    
    def __init__(self):
        self.initialized = False
        self.cleaned_up = False
    
    async def initialize(self):
        self.initialized = True
    
    async def execute(self, args, user_id=None):
        return {"result": f"Executed with {args.param1} and {args.param2}"}
    
    async def cleanup(self):
        self.cleaned_up = True


def test_base_tool_properties():
    """Test BaseTool properties."""
    tool = ConcreteTestTool()
    
    assert tool.name == "test_tool"
    assert tool.description == "Test tool implementation"
    assert tool.input_schema == TestToolInput
    assert tool.output_schema == TestToolOutput
    assert tool.required_roles == ["test_role"]


def test_base_tool_default_output_schema():
    """Test BaseTool has None as default output_schema."""
    
    class MinimalTool(BaseTool):
        name = "minimal"
        description = "Minimal tool"
        input_schema = TestToolInput
        
        async def execute(self, args, user_id=None):
            return {}
    
    tool = MinimalTool()
    assert tool.output_schema is None


def test_base_tool_default_required_roles():
    """Test BaseTool has empty list as default required_roles (public tool)."""
    
    class PublicTool(BaseTool):
        name = "public"
        description = "Public tool"
        input_schema = TestToolInput
        
        async def execute(self, args, user_id=None):
            return {}
    
    tool = PublicTool()
    assert tool.required_roles == []


@pytest.mark.asyncio
async def test_tool_lifecycle():
    """Test tool initialization, execution, and cleanup."""
    tool = ConcreteTestTool()
    
    # Initially not initialized
    assert tool.initialized is False
    
    # Initialize
    await tool.initialize()
    assert tool.initialized is True
    
    # Execute
    args = TestToolInput(param1="test", param2=20)
    result = await tool.execute(args, user_id="test-user")
    assert result["result"] == "Executed with test and 20"
    
    # Cleanup
    assert tool.cleaned_up is False
    await tool.cleanup()
    assert tool.cleaned_up is True


@pytest.mark.asyncio
async def test_tool_input_validation():
    """Test tool input validation with Pydantic."""
    tool = ConcreteTestTool()
    
    # Valid input
    valid_args = TestToolInput(param1="test", param2=15)
    result = await tool.execute(valid_args)
    assert "result" in result
    
    # Invalid input should raise ValidationError
    with pytest.raises(Exception):
        TestToolInput(param1=123)  # Wrong type for param1
    
    # Missing required field
    with pytest.raises(Exception):
        TestToolInput(param2=10)  # Missing param1


@pytest.mark.asyncio
async def test_tool_execute_with_user_id():
    """Test tool execute receives user_id parameter."""
    tool = ConcreteTestTool()
    
    # With user_id
    args = TestToolInput(param1="test")
    result = await tool.execute(args, user_id="user-123")
    assert result is not None
    
    # Without user_id (anonymous)
    result = await tool.execute(args, user_id=None)
    assert result is not None


def test_abstract_base_tool_cannot_instantiate():
    """Test BaseTool is abstract and cannot be instantiated directly."""
    
    # Should raise TypeError because execute() is not implemented
    with pytest.raises(TypeError):
        BaseTool()


def test_tool_must_implement_abstract_methods():
    """Test tool must implement all abstract methods and properties."""
    
    # Missing execute() method - should raise TypeError when instantiating
    with pytest.raises(TypeError):
        class IncompleteTool(BaseTool):
            name = "incomplete"
            description = "Incomplete tool"
            input_schema = TestToolInput
        
        IncompleteTool()  # This should raise TypeError
