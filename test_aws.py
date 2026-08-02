import boto3

ec2 = boto3.client("ec2")

response = ec2.describe_instances()

print("Connected successfully!")

for reservation in response["Reservations"]:
    for instance in reservation["Instances"]:

        print("----------------------------")
        print("Instance ID:", instance["InstanceId"])
        print("State:", instance["State"]["Name"])

        if "Tags" in instance:
            for tag in instance["Tags"]:
                if tag["Key"] == "Name":
                    print("Name:", tag["Value"])

        print("Instance Type:", instance["InstanceType"])

        if "PrivateIpAddress" in instance:
            print("Private IP:", instance["PrivateIpAddress"])