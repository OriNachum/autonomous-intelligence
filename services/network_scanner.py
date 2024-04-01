from scapy.all import ARP, Ether, srp

# Define the network range to scan
network = "192.168.1.0/24"

# Create an ARP packet

arp_packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network)

# Send the ARP packet and capture the responses
answered, unanswered = srp(arp_packet, timout=2, inter=0.1, verbose=False, iface="wlan0")

# Process the responses
devices = []
for sent, received in answered:
    devices.append({'ip': received.psrc, 'mac': received.hwsrc})

# Print the devices found
print("Available devices o nthe network:")
print("IP\t\tMAC Address")
for device in devices: 
    print("{}\t{}".format(devices['ip'], device['ip'], device['mac']))


