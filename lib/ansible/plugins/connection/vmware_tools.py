# (c) 2016 Deric Crago <deric.crago@gmail.com>
#
# This file is part of Ansible.
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import requests
import ssl
from ansible.errors import AnsibleError, AnsibleFileNotFound
from ansible.module_utils._text import to_bytes, to_native
from ansible.plugins.connection import ConnectionBase
from ansible.utils.path import makedirs_safe
from os.path import dirname, exists, getsize
from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim
from time import sleep


try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class Connection(ConnectionBase):
    ''' VMware Tools based connections '''

    transport = 'vmware_tools'

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        super(Connection, self).__init__(
            play_context, new_stdin, *args, **kwargs
        )
        display.vvv('in vmware_tools.__init__()')

    def set_host_overrides(self, host, hostvars=None):
        super(Connection, self).set_host_overrides(host, hostvars=hostvars)
        display.vvv('in vmware_tools.set_host_overrides()')

        connection_args = ['protocol', 'host', 'port', 'user', 'pwd',
                           'service', 'path']
        vm_args = ['username', 'password', 'uuid']

        self._vmware_tools_connection_kwargs = {}
        self._vmware_tools_vm_kwargs = {}

        for k, v in hostvars.items():
            if k.startswith('ansible_vmware_tools_connection_'):
                key = k.replace('ansible_vmware_tools_connection_', '')
                if key in connection_args:
                    if key == 'port':
                        self._vmware_tools_connection_kwargs[key] = int(v)
                    else:
                        self._vmware_tools_connection_kwargs[key] = v
            elif k.startswith('ansible_vmware_tools_vm_'):
                key = k.replace('ansible_vmware_tools_vm_', '')
                if key in vm_args:
                    self._vmware_tools_vm_kwargs[key] = v

    def _connect(self):
        super(Connection, self)._connect()
        display.vvv("in vmware_tools._connect()")

        if not self._connected:
            connection_kwargs = self._vmware_tools_connection_kwargs
            connection_kwargs['sslContext'] = None
            if hasattr(ssl, '_create_unverified_context'):
                sslContext = ssl._create_unverified_context()
                connection_kwargs['sslContext'] = sslContext

            try:
                si = SmartConnect(**connection_kwargs)
            except vim.fault.InvalidLogin:
                raise AnsibleError('Unable to Validate Host Credentials')

            if not si.content.sessionManager.currentSession:
                raise AnsibleError('vmware_tools connection failed')

            datacenter = None
            uuid = self._vmware_tools_vm_kwargs['uuid']
            vm_search = True
            instance_uuid = False
            vm = si.content.searchIndex.FindByUuid(
                datacenter, uuid, vm_search, instance_uuid
            )
            if not vm:
                raise AnsibleError('Unable to find VM by uuid')

            gom = si.content.guestOperationsManager
            auth_manager = gom.authManager
            vm_auth = vim.NamePasswordAuthentication(
                username=self._vmware_tools_vm_kwargs['username'],
                password=self._vmware_tools_vm_kwargs['password'],
                interactiveSession=False
            )

            try:
                auth_manager.ValidateCredentialsInGuest(vm=vm, auth=vm_auth)
            except vim.fault.InvalidGuestLogin:
                raise AnsibleError('Unable to Validate Guest Credentials')

            self._si = si
            self.vm = vm
            self.vm_auth = vm_auth
            self.file_manager = gom.fileManager
            self.process_manager = gom.processManager
            self._connected = True

    def close(self):
        super(Connection, self).close()
        display.vvv("in vmware_tools.close()")

        Disconnect(self._si)
        self._connected = False

    def _create_guest_program_spec(self, cmd, std_out_file, std_err_file):
        cmd_array = cmd.split(' ')
        program_path = cmd_array.pop(0)
        args = ' '.join(cmd_array)
        arguments = '{} 1> {} 2> {}'.format(args, std_out_file, std_err_file)

        guest_program_spec = vim.GuestProgramSpec()
        guest_program_spec.programPath = program_path
        guest_program_spec.arguments = arguments
        return guest_program_spec

    def _process_out_files(self, out_files):
        out_texts = {}
        for k, v in out_files.items():
            response = self._fetch_file(v)
            if response.status_code != 200:
                raise AnsibleError("Failed to fetch '{}' file".format(k))
            self.file_manager.DeleteFileInGuest(
                vm=self.vm, auth=self.vm_auth, filePath=v
            )
            out_texts[k] = response.text

        return out_texts

    def _wait_for_process_completion(self, pid):
        processes = self.process_manager.ListProcessesInGuest(
            vm=self.vm, auth=self.vm_auth, pids=[pid]
        )
        while len([p for p in processes if p.endTime is None]) > 0:
            sleep(1)
            processes = self.process_manager.ListProcessesInGuest(
                vm=self.vm, auth=self.vm_auth, pids=[pid]
            )

        return processes[0]

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super(Connection, self).exec_command(
            cmd, in_data=in_data, sudoable=sudoable
        )
        display.vvv('in vmware_tools.exec_command()')

        std_out_file = self.file_manager.CreateTemporaryFileInGuest(
            vm=self.vm, auth=self.vm_auth, prefix='std_out_', suffix='.file'
        )
        std_err_file = self.file_manager.CreateTemporaryFileInGuest(
            vm=self.vm, auth=self.vm_auth, prefix='std_err_', suffix='.file'
        )

        guest_program_spec = self._create_guest_program_spec(
            cmd=cmd, std_out_file=std_out_file, std_err_file=std_err_file
        )

        pid = self.process_manager.StartProgramInGuest(
            vm=self.vm, auth=self.vm_auth, spec=guest_program_spec
        )

        process = self._wait_for_process_completion(pid)

        out_texts = self._process_out_files({
            'std_out': std_out_file,
            'std_err': std_err_file
        })

        return [process.exitCode, out_texts['std_out'], out_texts['std_err']]

    def _fetch_file(self, guest_file_path):
        file_transfer_info = self.file_manager.InitiateFileTransferFromGuest(
            vm=self.vm, auth=self.vm_auth, guestFilePath=guest_file_path
        )

        return requests.get(file_transfer_info.url, stream=True, verify=False)

    def fetch_file(self, in_path, out_path):
        super(Connection, self).fetch_file(in_path, out_path)
        display.vvv('in vmware_tools.fetch_file()')

        makedirs_safe(dirname(out_path))

        response = self._fetch_file(in_path)

        if response.status_code != 200:
            raise AnsibleError('Failed to fetch file')

        if response.status_code == 200:
            with open(out_path, 'wb') as f:
                for chunk in response:
                    f.write(chunk)

    def _put_file(self, in_path, out_path, overwrite=True):
        guest_family = self.vm.guest.guestFamily
        if guest_family == 'linuxGuest':
            file_attributes = vim.GuestPosixFileAttributes()
        elif guest_family == 'windowsGuest':
            file_attributes = vim.GuestWindowsFileAttributes()
        else:
            raise AnsibleError(
                'Unrecognized guest family: {}'.format(guest_family)
            )

        return self.file_manager.InitiateFileTransferToGuest(
            vm=self.vm,
            auth=self.vm_auth,
            guestFilePath=out_path,
            fileAttributes=file_attributes,
            fileSize=getsize(in_path),
            overwrite=overwrite
        )

    def put_file(self, in_path, out_path):
        super(Connection, self).put_file(in_path, out_path)
        display.vvv('in vmware_tools.put_file()')

        if not exists(to_bytes(in_path, errors='surrogate_or_strict')):
            raise AnsibleFileNotFound(
                "file or module does not exist: {0}".format(to_native(in_path))
            )

        file_transfer_url = self._put_file(in_path, out_path)
        with open(in_path, 'rb') as f:
            r = requests.put(file_transfer_url, data=f, verify=False)

        if r.status_code != 200:
            raise AnsibleError('File transfer failed')
