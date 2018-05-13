#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018, Ansible Project
# Copyright: (c) 2018, Deric Crago <deric.crago@gmail.com>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = r'''
---
module: vmware_example
short_description: Example VMware Module with alternate syntax usage
description:
- This module is an example to show example syntax.
version_added: 2.6
author:
- Deric Crago (@dericcrago) <deric.crago@gmail.com>
requirements:
- python >= 2.6
- PyVmomi
options:
  vm:
    description:
    - The VM
extends_documentation_fragment: vmware.documentation
'''

EXAMPLES = r'''
- name: Get the VM by name
  vmware_example:
    host: blah
    username: blah
    password: blah
    port: 443
    validate_
    vm:
      name: VM_name
  delegate_to: localhost

- name: Get the VM by the DNS name for a virtual machine is the one returned from VMware tools, hostName
  vmware_example:
    vm:
      dns_name: dns_name.from.vcenter
  delegate_to: localhost

- name: Get the VM by the IP address for a virtual machine is the one returned from VMware tools, ipAddress
  vmware_example:
    vm:
      ip: 10.9.8.7
  delegate_to: localhost

- name: Get the VM by uuid
  vmware_example:
    vm:
      uuid: asdf-asdf-asdf-asfd
  delegate_to: localhost

- name: Get the VM by the inventory path
  vmware_example:
    vm:
      inventory_path: /path/relative/to/datacenter
  delegate_to: localhost

- name: Get the VM by the datastore path to the .vmx file for the virtual machine
  vmware_example:
    vm:
      datastore_path: /datastore/path/to/vm.vmx
  delegate_to: localhost
'''

RETURN = r'''
result:
    description: metadata about the found vm
    returned: always
    type: dict
    sample: {
        "esxi01": {
            "msg": "power down 'esxi01' to standby",
            "error": "",
        },
    }
'''


from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.vmware import vSphereHelper, get_inventory_path


def run_module():
    # define the available arguments/parameters that a user can pass to
    # the module
    module_args = dict(
        host=dict(type='str', required=True),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        port=dict(type='int', default=443),
        verify_ssl=dict(type='bool', default=True),
        datacenter=dict(type='raw', required=True),
        vm=dict(type='raw', required=True)
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        return result

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    vsphere_helper = vSphereHelper(module)
    vm = vsphere_helper.vm
    result["inventory_path_datacenter"] = get_inventory_path(vsphere_helper.datacenter)
    result["inventory_path_vm"] = get_inventory_path(vm)

    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    # if module.params['new']:
    #     result['changed'] = True

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    # if module.params['name'] == 'fail me':
    #     module.fail_json(msg='You requested this to fail', **result)
    if result.get('error', False):
        module.fail_json(msg='Problems with deleting the file, check for ambiguity.', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
