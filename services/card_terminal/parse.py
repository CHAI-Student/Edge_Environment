from payment import Protocol

hex = input()

hex.replace(" ", "")

raw_request = bytes.fromhex(hex)

request = Protocol.parse(raw_request)

print(request)