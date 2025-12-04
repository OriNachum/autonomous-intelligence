
import asyncio
import sys
import os

# Add parent directory to path to import wobble_head
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import wobble_head

class MockController:
    """Mock controller for testing"""
    def move_smoothly_to(self, **kwargs):
        # Mock implementation - just verify parameters
        pass

class MockTTSQueue:
    async def enqueue_text(self, text):
        print(f"Mock TTS: {text}")

async def test():
    print("Testing wobble_head with radius=0...")
    params = {'radius': 0, 'duration': 0.1, 'speed': 1}
    
    controller = MockController()
    
    # This test is now less relevant since we're using controller
    # But we can still verify the script executes without error
    try:
        await wobble_head.execute(
            controller,
            MockTTSQueue(),
            params
        )
        print("SUCCESS: wobble_head executed with new controller signature")
    except Exception as e:
        print(f"FAILURE: {e}")

    # Test with string "0"
    print("\nTesting wobble_head with radius='0'...")
    params = {'radius': '0', 'duration': '0.1', 'speed': '1'}
    try:
        await wobble_head.execute(
            controller,
            MockTTSQueue(),
            params
        )
        print("SUCCESS: wobble_head executed with string inputs")
    except Exception as e:
        print(f"FAILURE: {e}")

if __name__ == "__main__":
    asyncio.run(test())
