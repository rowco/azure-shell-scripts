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
args = parser.parse_args()
if not (args.subscription and args.resourcegroup):
  sys.exit(parser.print_usage())

subscriptionId = args.subscription
resourceGroupName = args.resourcegroup

def get_token():
  credential = DefaultAzureCredential()
  token = credential.get_token('https://management.azure.com')
  return token.token

#Get a token
token = get_token()
headers = {
  'Authorization': f"Bearer {token}",
}
async_results = {}

results = requests.get(f"https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Network/expressRouteCircuits?api-version=2022-05-01", headers=headers, verify=False)
circuits = results.json()['value']
print("Finding ExpressRoute Circuits:")

for circuit in circuits:
  circuitName = circuit['name']
  if not circuit['properties']['peerings']:
    continue
  peeringName = circuit['properties']['peerings'][0]['name']
  resourceGroupName = circuit['id'].split('/')[4]
  for devicePath in ['primary','secondary']:
    path_key = f"{resourceGroupName}/{circuitName}/{peeringName}/{devicePath}"
    print(path_key)
    async_results[path_key] = {}
    results = requests.post(f"https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/expressRouteCircuits/{circuitName}/peerings/{peeringName}/arpTables/{devicePath}?api-version=2022-05-01", headers=headers, verify=False)
    if results.status_code == 202:
      async_results[path_key]['arp'] = results.headers['Location']
    else:
      print(results.headers)
      sys.exit()
    results = requests.post(f"https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/expressRouteCircuits/{circuitName}/peerings/{peeringName}/routeTablesSummary/{devicePath}?api-version=2022-05-01", headers=headers, verify=False)
    if results.status_code == 202:
      async_results[path_key]['rts'] = results.headers['Location'] 
    else:
      print(results.headers)
      sys.exit()

for path_key in async_results:
    for part in async_results[path_key]:
      async_url = async_results[path_key][part]
      sleep_time = 0
      #Loop until result
      while True:
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(sleep_time)
        results = requests.get(async_url, headers=headers, verify=False)
        if results.status_code == 202:
          sleep_time = int(results.headers['Retry-After'])
          continue
        else:
          break
      async_results[path_key][part] = results.json()
sys.stdout.write('\r')


table = {}
for path_key in async_results:
  if not async_results[path_key]['arp']['value']:
    arp = { 'ipAddress':'--', 'macAddress':'--'}
  else:
    arp = async_results[path_key]['arp']['value'][0]
  table[path_key] = [
    path_key,
    arp['ipAddress'],
    arp['macAddress'],
    async_results[path_key]['rts']['value'][0]['as'],
    async_results[path_key]['rts']['value'][0]['upDown'],
    async_results[path_key]['rts']['value'][0]['statePfxRcd'],
    async_results[path_key]['rts']['value'][-1]['statePfxRcd'],
  ]

headers = [
  "Peering",
  "Peer",
  "Mac",
  "Peer AS",
  "Time",
  "Routes Learnt",
  "Routes Sent"
]

print(tabulate(table.values(),headers=headers))