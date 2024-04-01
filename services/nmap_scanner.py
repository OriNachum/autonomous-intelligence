import nmap

nm = nmap.PortScanner()

network = '192.168.1.0/24'

nm.scan(hosts=network, arguments='-sn')

# Print the devices found
print("Available devices o nthe network:")
print("IP\t\tMAC Address")
for host in nm.all_hosts(): 
    if 'mac' in nm[host]['addresses']:
        print(f"{host}\t{nm[host]['adresses']['mac']}")
    else:
        print(f"{host}\tMAC Address Unavailable")

