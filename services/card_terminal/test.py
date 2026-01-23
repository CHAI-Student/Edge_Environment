import asyncio
import logging
import sys

from datetime import datetime

from payment import CommunicationManager


logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

class InteractiveUI:
    """Interactive command-line interface for card terminal operations"""

    def __init__(self, communication_handler: CommunicationManager):
        self.communication_handler = communication_handler
        self.commands = {
            "help": self.cmd_help,
            "send": self.cmd_send,
            "pc": self.cmd_health_check,
            "clear": self.cmd_clear,
            "exit": self.cmd_exit,
        }

    def display_menu(self):
        """Display main menu"""
        print("\n" + "=" * 50)
        print("Card Terminal Interactive Interface")
        print("=" * 50)
        print("\nAvailable Commands:")
        print("  pc         - Health Check (PC, 10)")
        print("  send       - Send raw message (service_code message_type)")
        print("  clear      - Clear screen")
        print("  help       - Show this menu")
        print("  exit       - Exit program")
        print("-" * 50)

    def cmd_help(self, *args):
        """Display help menu"""
        self.display_menu()

    def cmd_clear(self, *args):
        """Clear screen"""
        print("\033[2J\033[H", end="")

    def cmd_exit(self, *args):
        """Exit program"""
        print("\nExiting...")
        sys.exit(0)

    async def cmd_send(self, *args):
        """Send raw message: send SERVICE_CODE MESSAGE_TYPE [payload_key1=value1 ...]"""
        if len(args) < 2:
            print("Usage: send SERVICE_CODE MESSAGE_TYPE [payload options]")
            print("Example: send PS 10")
            return

        service_code = args[0]
        message_type = int(args[1])
        payload_args = dict(arg.split("=") for arg in args[2:] if "=" in arg)

        await self._send_message(service_code, message_type, payload_args)

    async def cmd_health_check(self, *args):
        """Send Health Check message (PC, 10)"""
        print("\nSending Health Check (PC, 10)...")
        await self._send_message("PC", 0, {"message": ""})

    async def _send_message(self, service_code, message_type, payload_args):
        """Send a message to the queue"""
        try:
            await self.communication_handler.write(
                service_code, message_type, payload_args
            )
            print("✓ Message queued successfully")
        except Exception as e:
            print(f"Error building message: {e}")

    async def run_interactive(self):
        """Run interactive command loop"""
        self.display_menu()

        loop = asyncio.get_event_loop()

        while True:
            try:
                user_input = await loop.run_in_executor(None, input, "\n> ")

                if not user_input.strip():
                    continue

                parts = user_input.strip().split()
                cmd = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else ()

                if cmd not in self.commands:
                    print(
                        f"Unknown command: {cmd}. Type 'help' for available commands."
                    )
                    continue

                handler = self.commands[cmd]
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args)
                else:
                    handler(*args)

            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")


async def handle_protocol(comm: CommunicationManager):
    """Main protocol handler to manage reading and writing tasks"""

    try:
        while True:
            try:
                received_request = await comm.read()

                service_code = received_request["service_code"]
                message_type = received_request["message_type"]

                #########
                # Token #
                #########
                if service_code == "PS" and message_type == 0:
                    await comm.write(
                        service_code="TQ", message_type=0, payload={}
                    )

                if service_code == "TQ" and message_type == 1:
                    tq_payload = received_request["payload"]
                    print("\nReceived TQ Payload:", tq_payload)

                    if tq_payload.status != "Y":
                        print("TQ Response indicates failure, aborting further processing.")
                        continue

                    vankey_hash = tq_payload.get("vankey_hash", b"")

                    await comm.write(
                        service_code="D8",
                        message_type=0,
                        payload={"amount": "1000", "vankey_hash": vankey_hash},
                    )

                if service_code == "D8" and message_type == 1:
                    d8_payload = received_request["payload"]
                    print("\nReceived D8 Payload:", d8_payload)

                    if d8_payload.status != "Y":
                        print("D8 Response indicates failure, aborting further processing.")
                        continue

                    await comm.write(
                        service_code="D9",
                        message_type=0,
                        payload={
                            "amount": "1000",
                            "original_authorization_number": d8_payload.get(
                                "authorization_number", b""
                            ),
                            "original_authorization_date": datetime.now().strftime(
                                "%y%m%d"
                            ),
                            "vankey_hash": tq_payload.get("vankey_hash", b""),
                        },
                    )

                ###############
                # Samsung Pay #
                ###############
                elif service_code == "PA" and message_type == 0:
                    await comm.write(
                        service_code="D1",
                        message_type=0,
                        payload={"amount": "1000", "authorization_type": "APPROVAL", "message": "야스"},
                    )
                
                elif service_code == "D1" and message_type == 1:
                    d1_payload = received_request["payload"]
                    print("\nReceived D1 Payload:", d1_payload)

                    if d1_payload.status != "Y":
                        print("D1 Response indicates failure, aborting further processing.")
                        continue

                    await comm.write(
                        service_code="D7",
                        message_type=0,
                        payload={
                            "amount": "1000",
                            "original_authorization_number": d1_payload.get(
                                "authorization_number", b""
                            ),
                            "original_authorization_date": datetime.now().strftime(
                                "%y%m%d"
                            ),
                            "vankey": d1_payload.get("vankey", b""),
                        },
                    )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error in protocol handling loop: %s", e)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Closing protocol handler")


async def run_server(comm: CommunicationManager):
    """Run the asyncio server to accept client connections"""
    global connection_active
    try:
        server = await asyncio.start_server(comm.run, "0.0.0.0", 5000)
        print("Server running on port 5000...")
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")
        connection_active = False


async def main():
    """Main entry point"""
    comm = CommunicationManager()

    ui = InteractiveUI(comm)
    ui_task = asyncio.create_task(ui.run_interactive())
    server_task = asyncio.create_task(run_server(comm))
    protocol_task = asyncio.create_task(handle_protocol(comm))

    try:
        await asyncio.gather(ui_task, server_task, protocol_task)
    except Exception as e:
        print(f"Main error: {e}")
    finally:
        ui_task.cancel()
        server_task.cancel()
        protocol_task.cancel()
        await asyncio.gather(
            ui_task, server_task, protocol_task, return_exceptions=True
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        exit(0)
