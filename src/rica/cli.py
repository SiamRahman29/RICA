"""Command-line interface for RICA."""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

from .core.assistant import RICA
from .core.config import Config


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="RICA - Rather Intelligent Conversational Assistant with Speech-to-Text and Text-to-Speech capabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rica                    # Start interactive mode
  rica --voice           # Start voice-only mode
  rica --text            # Start text-only mode
  rica --config config.env # Use custom config file
  rica --status          # Show system status
        """
    )
    
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Enable voice input/output mode"
    )
    
    parser.add_argument(
        "--text",
        action="store_true",
        help="Enable text-only mode"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show system status and exit"
    )
    
    parser.add_argument(
        "--test-audio",
        action="store_true",
        help="Test audio system components"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for API server (default: 127.0.0.1)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for API server (default: 8000)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)"
    )
    
    return parser


async def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        # Load configuration
        if args.config:
            config_path = Path(args.config)
            if not config_path.exists():
                print(f"Error: Configuration file not found: {config_path}")
                return 1
            
            # Load config from file
            config = Config(_env_file=config_path)
        else:
            config = Config()
        
        # Override config with CLI arguments
        if args.host:
            config.host = args.host
        if args.port:
            config.port = args.port
        if args.debug:
            config.debug = args.debug
        if args.log_level:
            config.log_level = args.log_level
        
        # Initialize assistant
        assistant = RICA(config)
        
        # Handle different modes
        if args.status:
            await show_status(assistant)
            return 0
        
        if args.test_audio:
            await test_audio_system(assistant)
            return 0
        
        if args.text:
            await run_text_mode(assistant)
        elif args.voice:
            await run_voice_mode(assistant)
        else:
            await run_interactive_mode(assistant)
        
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            logging.exception("Detailed error information:")
        return 1


async def show_status(assistant: RICA) -> None:
    """Show system status."""
    print("RICA - System Status")
    print("=" * 40)
    
    status = assistant.get_status()
    
    print(f"Status: {status['status']}")
    print(f"OpenAI Model: {status['config']['openai_model']}")
    print(f"Audio Sample Rate: {status['config']['audio_sample_rate']}")
    print(f"Host: {status['config']['host']}")
    print(f"Port: {status['config']['port']}")
    
    print(f"\nRegistered Agents: {', '.join(status['agents'])}")
    
    # Audio status
    audio_status = status['audio_status']
    print(f"\nAudio System:")
    print(f"  Initialized: {audio_status['initialized']}")
    print(f"  Recording: {audio_status['recording']}")
    print(f"  Input Devices: {len(audio_status['audio_devices']['input_devices'])}")
    print(f"  Available Voices: {audio_status['audio_devices']['output_devices']}")


async def test_audio_system(assistant: RICA) -> None:
    """Test audio system components."""
    print("Testing Audio System...")
    print("=" * 30)
    
    try:
        await assistant.start()
        
        # Test audio components
        test_results = await assistant.audio_manager.test_audio_system()
        
        print("\nTest Results:")
        for component, result in test_results.items():
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"  {component}: {status}")
        
        if test_results["overall"]:
            print("\n🎉 All audio tests passed!")
        else:
            print("\n❌ Some audio tests failed. Check the logs for details.")
            
    except Exception as e:
        print(f"Error testing audio system: {e}")
    finally:
        await assistant.stop()


async def run_text_mode(assistant: RICA) -> None:
    """Run in text-only mode."""
    print("RICA - Text Mode")
    print("=" * 30)
    print("Type 'quit' to exit")
    print()
    
    try:
        await assistant.start()
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    break
                
                if not user_input:
                    continue
                
                # Process text input
                response = await assistant.process_text_input(user_input)
                print(f"RICA: {response}")
                print()
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
                
    finally:
        await assistant.stop()
        print("Goodbye!")


async def run_voice_mode(assistant: RICA) -> None:
    """Run in voice-only mode."""
    print("RICA - Voice Mode")
    print("=" * 30)
    print("Press Ctrl+C to exit")
    print()
    
    try:
        await assistant.start()
        
        while True:
            try:
                print("Listening... (speak now)")
                
                # Process voice input and generate response
                response = await assistant.process_conversation()
                
                print(f"Response: {response}")
                print("-" * 30)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
                
    finally:
        await assistant.stop()
        print("Goodbye!")


async def run_interactive_mode(assistant: RICA) -> None:
    """Run in interactive mode with both voice and text options."""
    print("RICA - Interactive Mode")
    print("=" * 35)
    print("Commands:")
    print("  'voice' - Switch to voice input")
    print("  'text'  - Switch to text input")
    print("  'status' - Show system status")
    print("  'quit'  - Exit")
    print()
    
    try:
        await assistant.start()
        
        # Start with text mode
        current_mode = "text"
        
        while True:
            try:
                if current_mode == "text":
                    user_input = input("You: ").strip()
                    
                    if user_input.lower() in ['quit', 'exit', 'bye']:
                        break
                    elif user_input.lower() == 'voice':
                        current_mode = "voice"
                        print("Switched to voice mode. Say 'text' to switch back.")
                        continue
                    elif user_input.lower() == 'status':
                        await show_status(assistant)
                        continue
                    elif not user_input:
                        continue
                    
                    # Process text input
                    response = await assistant.process_text_input(user_input)
                    print(f"RICA: {response}")
                    print()
                    
                else:  # voice mode
                    print("Listening... (say 'text' to switch to text mode)")
                    
                    try:
                        # Process voice input and generate response
                        response = await assistant.process_conversation()
                        
                        print(f"Response: {response}")
                        print("-" * 30)
                        
                        # Check if user wants to switch modes
                        if "text" in response.lower():
                            current_mode = "text"
                            print("Switched to text mode.")
                            
                    except Exception as e:
                        print(f"Voice processing error: {e}")
                        continue
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
                
    finally:
        await assistant.stop()
        print("Goodbye!")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
