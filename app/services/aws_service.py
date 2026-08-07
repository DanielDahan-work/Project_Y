import os
import boto3


def get_servers():

    ec2 = boto3.client(
        "ec2",
        region_name="eu-central-1"
    )

    servers = []

    response = ec2.describe_instances()

    for reservation in response["Reservations"]:

        for instance in reservation["Instances"]:

            name = "Unknown"

            if "Tags" in instance:

                for tag in instance["Tags"]:

                    if tag["Key"] == "Name":
                        name = tag["Value"]

            servers.append({
                "id": instance["InstanceId"],
                "name": name,
                "role": "AWS EC2",
                "os": "Ubuntu",
                "instance_type": instance["InstanceType"],
                "private_ip": instance.get("PrivateIpAddress", "-"),
                "status": instance["State"]["Name"].capitalize(),
                "security_group": instance["SecurityGroups"][0]["GroupName"],
                "launch_time": instance["LaunchTime"]
            })

    return servers