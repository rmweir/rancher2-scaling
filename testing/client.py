import yaml
import urllib3
import requests
import time

from rancher import Client as RancherClient, ApiError
from kubernetes.client import ApiClient, Configuration, CustomObjectsApi
from kubernetes.config.kube_config import KubeConfigLoader
from common import random_str

urllib3.disable_warnings()


class Auth:
    def __init__(self, token, url):
        self.url = url + "/v3"
        self.k8s_proxy_url = url + "/k8s/clusters/local/"
        self.k8s_url = url + ":6443"
        self.token = token
        self.k8s_token = token

    def set_k8s_token(self, token):
        self.k8s_token = token


class Client:
    def __init__(self, auth):
        urllib3.disable_warnings()
        self.Auth = auth

        self.k8s_client = k8s_api_client(self, "local")
        session = requests.Session()
        session.verify = False
        self.session = session

    def rancher_secrets(self):
        return self._list_rancher("k8s/clusters/local/api/v1/secrets")

    def timed_list_k8s_clusters_no_resp(self):
        return self._timed_list_k8s("clusters")

    def timed_list_k8s_projects_no_resp(self):
        return self._timed_list_k8s("projects")

    def timed_list_rancher_clusters(self):
        try:
            a = self.rancher_api_client()
            start1 = time.perf_counter()
            resp = a.list_project_role_template_binding(limit=-1)
        except ApiError as e:
            print(e)
            return
        end = time.perf_counter() - start1
        return {"num_clusters": len(resp["data"]), "rancher_cluster_list_time": end}

    def timed_list_rancher_projects_no_resp(self):
        try:
            a = self.rancher_api_client()
            start = time.thread_time()
            resp = a.list_project(limit=-1)
        except ApiError as e:
            print(e)
            return
        end = time.thread_time() - start
        return {"num_projects": len(resp["data"]), "rancher_project_list_time": end}

    def timed_crud_rancher_cluster(self):
        try:
            start = time.time()
            rancher_client = self.rancher_api_client()
            proj = rancher_client.create_project(
                name="p-" + random_str(),
                clusterId="local")
            create_time = time.time() - start
            start = time.time()
            rancher_client.by_id_project(
                id=proj.id)
            get_time = time.time() - start
            start = time.time()
            rancher_client.update_by_id_project(
                id=proj.id,
                description="asd")
            update_time = time.time() - start
            proj = rancher_client.reload(proj)
            start = time.time()
            rancher_client.delete(proj)
            delete_time = time.time() - start
        except ApiError:
            return {}

        times = {
            "rancher_create_time": create_time,
            "rancher_get_time": get_time,
            "rancher_update_time": update_time,
            "rancher_delete_time": delete_time
        }
        return times

    def timed_create_rancher_cluster(self, name):
        return self._timed_create_rancher(
            "kontainerdriver",
            body={
                "name": name,
                "url": random_str(),
                "type": "kontainerdriver"})

    def _timed_list_k8s(self, resource_plural):
        k8s = k8s_api_client(self, "local")
        start = time.time()
        resp = k8s.call_api(
            '/apis/{group}/{version}/{plural}',
            "GET",
            {
                'group': 'management.cattle.io',
                'version': 'v3',
                'plural': resource_plural
            },
            header_params={
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + self.Auth.token
            },
            auth_settings=['BearerToken'],
            _preload_content=True,
            response_type='object',
        )
        elapsed = time.time() - start
        if resp[1] == 200:
            return {"num_k8s_" + resource_plural: len(resp[0].get("items", {})),
                    "k8s_" + resource_plural[:-1] + "_list_time": elapsed}
        else:
            return None

    # was using rancher client for this before but there appeared to be an issue with one request, no matter how many
    # were sent, not returning. Appeared to be an issue with rancher api's 'send'
    def _list_rancher(self, resource):
        """gets rancher resource"""
        resp = self.rancher_kube_client.call_api(
            "/" + resource,
            "GET",
            header_params={
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + self.Auth.token
            },
            _return_http_data_only=True,
            response_type='object'
        )
        return resp

    def _list_k8s_proxy(self, version, resource):
        client_configuration = type.__call__(Configuration)
        client_configuration.host = self.Auth.k8s_proxy_url
        client_configuration.verify_ssl = False
        rancher_client = ApiClient(configuration=client_configuration)
        resp = rancher_client.call_api(
            "api/" + version + "/" + resource,
            "GET",
            header_params={
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + self.Auth.token
            },
            _return_http_data_only=True,
            response_type='object'
        )
        return resp

    def list_k8s(self, resource):
        resp = self.k8s_client.call_api(
            '/apis/{group}/{version}/{plural}',
            "GET",
            {
                'group': 'management.cattle.io',
                'version': 'v3',
                'plural': resource
            },
            header_params={
                'Accept': 'application/json',
                'Authorization': 'Bearer ' + self.Auth.k8s_token
            },
            auth_settings=['BearerToken'],
            _return_http_data_only=True,
            _preload_content=True,
            response_type='object'
        )
        return resp

    def list_proxy_secrets(self):
        return self._list_k8s_proxy("v1", "secrets")

    def rancher_api_client(self):
        return RancherClient(
            url=self.Auth.url,
            token=self.Auth.token,
            verify=False)
            # headers={"Accept-Encoding": "gzip"})


# should just add this to rancher client, exists in a
# few projects using rancher client
def k8s_api_client(client, cluster_name, kube_path=None):
    kube_path = None
    if kube_path is not None:
        kube_file = open(kube_path, "r")
        kube_config = kube_file.read()
        kube_file.close()
    else:
        cluster = client.rancher_api_client().by_id_cluster(cluster_name)
        kube_config = cluster.generateKubeconfig().config

    loader = KubeConfigLoader(config_dict=yaml.full_load(kube_config))

    client_configuration = type.__call__(Configuration)
    loader.load_and_set(client_configuration)
    client_configuration.api_key = {}
    client_configuration.verify_ssl = False
    k8s_client = ApiClient(configuration=client_configuration)
    return CustomObjectsApi(api_client=k8s_client).api_client


# create rancher client using k8s client modules
def rancher_kube_api_client(auth):
    client_configuration = type.__call__(Configuration)
    client_configuration.host = auth.url
    client_configuration.verify_ssl = False
    return ApiClient(configuration=client_configuration)
