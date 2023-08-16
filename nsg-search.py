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

def get_token():
  credential = DefaultAzureCredential()
  token = credential.get_token('https://management.azure.com')
  return token.token

#Get a token
token = get_token()
headers = {
  'Authorization': f"Bearer {token}",
}

include_default = False

def make_network(ip_str):
    
  try:
    return ipaddress.ip_network(ip_str)
  except ValueError:
    interface = ipaddress.ip_interface(ip_str)
    return interface.network
  except:
    raise ValueError

try:
  filter = make_network(sys.argv[1])
except:
  print('Does not look like an ip address')
  sys.exit()

print(f"Looking for {filter}")

nsgs = {}

results = requests.get(f"https://management.azure.com/subscriptions?api-version=2022-12-01", headers=headers, verify=False)
result_json = results.json()
subscriptions = { s['subscriptionId']: s for s in result_json['value'] }
for subid in subscriptions:
  #print(subscriptions[subid]['displayName'])
  results = requests.get(f"https://management.azure.com/subscriptions/{subid}/providers/Microsoft.Network/networkSecurityGroups?api-version=2023-02-01", headers=headers, verify=False)
  #print(results)


  results_json = results.json()
  if not results_json:
    continue
  nsgs = results_json['value']
  for nsg in nsgs:
    #print(f"NSG: {nsg['name']}")
    for rule in nsg['properties']['securityRules']:

      prop = rule['properties']
      if 'sourceAddressPrefix' in prop:
        s = [prop['sourceAddressPrefix']]
      elif 'sourceAddressPrefixes' in prop:
        s = prop['sourceAddressPrefixes']

      if 'destinationAddressPrefix' in prop:
        d = [prop['destinationAddressPrefix']]
      elif 'destinationAddressPrefixes' in prop:
        d = prop['destinationAddressPrefixes']

      def compare_prefixes(prefixes,network):
        match = False
        for i in prefixes:
          try:
            if i == '*' and include_default:
              n = make_network('0.0.0.0/0')
            if i == '0.0.0.0/0' and not include_default:
              continue
            else:
              n = make_network(i)

            if network.overlaps(n):
              match = True
          except:
            continue
        return match

      s_match = compare_prefixes(s,filter)
      d_match = compare_prefixes(d,filter)
      
      if s_match or d_match:
        print(f"SUB: {subscriptions[subid]['displayName']} NSG: {nsg['name']} RULE: {rule['name']} - {s} / {d} - {s_match} / {d_match}")
      #print(f"PROPERITES: {rule['properties']}")



