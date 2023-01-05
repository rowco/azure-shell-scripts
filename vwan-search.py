#! /usr/bin/env python

import requests
from pprint import pprint
import urllib3
import sys
import time
import ipaddress
import argparse
import os
from tabulate import tabulate
# pip install azure-identity

from azure.identity import DefaultAzureCredential

urllib3.disable_warnings()

parser = argparse.ArgumentParser(description='ExpressRoute status script')
parser.add_argument('-s','--subscription', default=os.environ.get('SUBSCRIPTION'),help="Subscription of the VWAN")
parser.add_argument('-r','--resourcegroup', default=os.environ.get('RESOURCEGROUP'),help="Resource Group of the VWAN")
parser.add_argument('-m','--match',help="IP prefix to look for.")
args = parser.parse_args()
if not (args.subscription and args.resourcegroup):
  sys.exit(parser.print_usage())

subscriptionId = args.subscription
resourceGroupName = args.resourcegroup

def get_token():
  credential = DefaultAzureCredential()
  token = credential.get_token('https://management.azure.com')
  return token.token

#Basic search filtering
if args.match:
  print(f"showing filtered: {args.match}")

  try:
    filter = ipaddress.ip_network(args.match)
  except ValueError:
    interface = ipaddress.ip_interface(args.match)
    filter = interface.network
  except:
    print("Doesn't look like an IP address or network")
    sys.exit()
else:
  filter = False

#Get a token
token = get_token()
headers = {
  'Authorization': f"Bearer {token}",
}

async_results = {}

# Fetch virtualHubs
results = requests.get(f"https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Network/virtualHubs?api-version=2021-05-01", headers=headers, verify=False)
virtual_hubs = results.json()['value']
vhub_names = [ v['name'] for v in virtual_hubs ]

for virtualHubName in vhub_names:

  async_results[virtualHubName] = {}

  # Fetch routetables
  results = requests.get(f"https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualHubs/{virtualHubName}/hubRouteTables?api-version=2021-05-01", headers=headers, verify=False)
  route_tables = results.json()['value']

  for table in route_tables:

    #Only use the default table for now
    if table['name'] != 'defaultRouteTable':
      continue
    
    print(f"Finding routes for {virtualHubName} table: {table['name']}")
    data = {
      "virtualWanResourceType": "RouteTable",
      "resourceid": table['id']
    }
    results = requests.post(f"https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualHubs/{virtualHubName}/effectiveRoutes?api-version=2021-05-01",json=data, headers=headers, verify=False)
    
    if results.status_code != 202:
      print("Unexpected return code")
      print(results.text)
      print(results.headers)
      sys.exit()

    # Store the async url for each hub/table
    async_results[virtualHubName][table['name']] = results.headers['Azure-AsyncOperation']


for virtualHubName in async_results:
  for table in async_results[virtualHubName]:
    async_url = async_results[virtualHubName][table]
    sleep_time = 0

    while True:
      #Loop until result
      #print(f"sleeping for {sleep_time}")
      time.sleep(sleep_time)
      results = requests.get(async_url, headers=headers, verify=False)
      if results.json()['status'] == 'InProgress':
        sleep_time = int(results.headers['Retry-After'])
        continue
      else:
        break

    data = results.json()
    matches = []
    for net in data['properties']['output']['value']:

      prefix = ipaddress.ip_network(net['addressPrefixes'][0])
      descr = f"{prefix} - {net['nextHopType']}\n\tNext Hop: {net['nextHops'][0]}\n\tOrigin: {net['routeOrigin']}"

      if filter:
        if prefix.overlaps(filter):
          matches.append(descr)
      else:
        matches.append(descr)

    if matches:
      print(f"\n\nMatched {len(matches)} prefix for {virtualHubName} table: {table}")
      for i in matches:
        print(i)
