def get_servers():

    servers = [

{
    "id": "i-08f2c1ab123456789",
    "name": "PX-VPN-01",
    "role": "WireGuard Gateway",

    "os": "Ubuntu Server 24.04 LTS",

    "instance_type": "t3.micro",

    "private_ip": "10.50.1.10",

    "public_ip": "18.194.120.15",

    "region": "eu-central-1",

    "availability_zone": "eu-central-1a",

    "security_group": "PX-VPN-SG",

    "volume": "50 GB gp3",

    "status": "running"
},

        {
            "name": "PX-NAS-01",
            "role": "Samba Storage",
            "os": "Ubuntu 24.04",
            "instance_type": "t3.micro",
            "private_ip": "10.50.2.10",
            "status": "Online"
        },

        {
            "name": "PX-Jenkins-01",
            "role": "CI/CD Server",
            "os": "Ubuntu 24.04",
            "instance_type": "t3.micro",
            "private_ip": "10.50.3.10",
            "status": "Online"
        }

    ]

    return servers