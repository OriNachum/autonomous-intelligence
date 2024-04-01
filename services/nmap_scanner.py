import nmap

# Initialize Nmap PortScanner
nm = nmap.PortScanner()

# Define the network range you want to scan
network = '192.168.1.0/24'

# Perform a scan with OS and service version detection
# -O: Enable OS detection
# -sV: Probe open ports to determine service/version info
# --host-timeout: Times out if scanning a single host takes longer than specified (optional, for speed-up)
nm.scan(hosts=network, arguments='-O -sV --host-timeout 1m')

for host in nm.all_hosts():
    print(f"Host : {host} ({nm[host].hostname()})")
    print(f"State : {nm[host].state()}")

    for proto in nm[host].all_protocols():
        print(f"----------")
        print(f"Protocol : {proto}")

        lport = nm[host][proto].keys()
        sorted(lport)
        for port in lport:
            print(f"port : {port}\tstate : {nm[host][proto][port]['state']}, service: {nm[host][proto][port]['name']}")

    # OS detection
    if 'osclass' in nm[host]:
        for osclass in nm[host]['osclass']:
            print('OS Details:')
            print(f"Type : {osclass['type']}, Vendor : {osclass['vendor']}, OS Family : {osclass['osfamily']}, OS Gen : {osclass['osgen']}")
            print(f"Accuracy : {osclass['accuracy']}%")
    else:
        print("OS Details: Not available")

    print("----------\n")
