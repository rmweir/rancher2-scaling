import client as c
import timeit
import json
import os
import time
import random
import common
import requests

from multiprocessing import Pool, Manager, cpu_count, Process
from options import Options
from pandas import DataFrame


label_to_index = {}


class Metric:
    def __init__(self, fn, labels):
        self.fn = fn
        self.labels = labels


processes = []
m = Manager()
results = m.dict()


class TestBench:
    def __init__(self, metrics, options):
        global results
        m = Manager()

        # Setup state
        for metric in metrics:
            for label in metric.labels:
                label_to_index[label] = len(label_to_index.keys())
        """
        with Pool() as pool:
            first_write = True
            last_save = time.time()
            for i in range(options.iterations):
                results[i] = m.Array('f', [-1 for _ in range(len(label_to_index.keys()))])
                for metric in metrics:
                    pool.apply_async(metric.fn, args=(i, results))
                time.sleep(options.pulse + random.uniform(0, options.jitter))
                if time.time() - last_save > options.save_every:
                    print("saving...")
                    pool.close()
                    pool.join()

                    save(results, first_write)
                    results = {}
                    last_save = time.time()
                    print("saved...")
                    pool = Pool()
                    first_write = False
            pool.close()
            pool.join()
            save(results, first_write)
        """
        threads = []
        for i in range(options.iterations):
            # threads = []
            results[i] = m.Array('f', [-1 for _ in range(len(label_to_index.keys()))])

            for metric in metrics:
                thread = Process(target=metric.fn, args=(i, results))
                threads.append(thread)
                thread.start()
            time.sleep(options.pulse + random.uniform(0, options.jitter))
        for thread in threads:
            thread.join()




def log_dict(result, results):
    if result is None:
        return
    row_key = result.get("row_key", None)
    if row_key is None:
        return
    del result["row_key"]
    for key in result.keys():
        col_index = label_to_index.get(key, None)
        if col_index is not None:
            a = results
            results[row_key][col_index] = result[key]


def test_k8s_cluster_list(row_index, results):
    k8s_cluster_test_data = {"row_key": row_index}
    k8s_cluster_test_data.update(client.timed_list_k8s_clusters_no_resp())
    log_dict(k8s_cluster_test_data, results)


def test_rancher_cluster_list(row_index):
    cluster_test_data = {"row_key": row_index}
    cluster_test_data.update(client.timed_list_rancher_clusters())
    return cluster_test_data


def test_rancher_cluster_list_sync(row_index, results):
    cluster_test_data = {"row_key": row_index}
    cluster_test_data.update(client.timed_list_rancher_clusters())
    log_dict(cluster_test_data, results)


def test_rancher_project_list(row_index):
    global results
    project_test_data = {"row_key": row_index}
    project_test_data.update(client.timed_list_rancher_projects_no_resp())
    log_dict(project_test_data)


def test_rancher_project_list_sync(row_index, data):
    project_test_data = {"row_key": row_index}
    project_test_data.update(client.timed_list_rancher_projects_no_resp())
    log_dict(project_test_data, data)

def test_rancher_project_list_sync2(row_index, data):
    project_test_data = {"row_key": row_index}
    cookies = {
        'CSRF': 'fdbe00a4cc',
        'R_USERNAME': 'admin',
        'R_SESS': 'token-z4c4j:khskn7t2d5rkgltfs4zrjcgts2v5wqbfgk5997ltzvvbpd5hrv7nj8',
    }

    headers = {
        'Connection': 'keep-alive',
        'x-api-no-challenge': 'true',
        'accept': 'application/json',
        'x-api-action-links': 'actionLinks',
        'x-api-csrf': 'fdbe00a4cc',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36',
        'content-type': 'application/json',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Referer': 'https://64.225.33.218.xip.io/c/local/projects-namespaces',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    params = (
        ('limit', '-1'),
        ('sort', 'name'),
    )
    start = time.time()
    response = requests.get('https://64.225.33.218.xip.io/v3/projects?limit=-1&sort=name', headers=headers,
                            cookies=cookies, verify=False)
    elapsed = time.time() - start
    update_dict = {"rancher_project_list_time": elapsed}
    project_test_data.update(update_dict)
    log_dict(project_test_data, data)


def test_k8s_project_list(row_index, data):
    k8s_project_test_data = {"row_key": row_index}
    k8s_project_test_data.update(client.timed_list_k8s_projects_no_resp())
    log_dict(k8s_project_test_data, data)


def test_rancher_crud(row_index, data):
    crud_data = {"row_key": row_index}
    try:
        crud_times = client.timed_crud_rancher_cluster()
        crud_data.update(crud_times)
    except Exception as e:
        print("ERROR crud", e)
    log_dict(crud_data, data)


def save(progress, write_columns):
    header = write_columns

    def proxy_to_array(proxy_array):
        arr = []
        for i in proxy_array:
            arr += [i]
        return arr
    for key in progress.keys():
        new_arr = progress[key]
        progress[key] = proxy_to_array(new_arr)
    current = DataFrame.from_dict(progress.copy(), orient="index", columns=label_to_index.keys())
    current.to_csv(path_or_buf="scale_test.csv", mode="a", header=header)


metrics = [
    Metric(test_rancher_cluster_list_sync, ["rancher_cluster_list_time", "num_clusters"]),
    Metric(test_rancher_project_list_sync, ["rancher_project_list_time", "num_projects"]),
    Metric(test_k8s_cluster_list, ["k8s_cluster_list_time", "num_k8s_clusters"]),
    Metric(test_k8s_project_list, ["k8s_project_list_time", "num_k8s_projects"]),
    Metric(test_rancher_crud, ["rancher_create_time", "rancher_get_time",
                               "rancher_update_time", "rancher_delete_time"])
]

token = os.getenv("RANCHER_SCALING_TOKEN")
url = os.getenv("RANCHER_SCALING_URL")
a = c.Auth(token, url)
client = c.Client(a)
opts = Options()
TestBench(metrics, opts)


cookies = {
    'CSRF': 'fdbe00a4cc',
    'R_USERNAME': 'admin',
    'R_SESS': 'token-z4c4j:khskn7t2d5rkgltfs4zrjcgts2v5wqbfgk5997ltzvvbpd5hrv7nj8',
}

headers = {
    'Connection': 'keep-alive',
    'x-api-no-challenge': 'true',
    'accept': 'application/json',
    'x-api-action-links': 'actionLinks',
    'x-api-csrf': 'fdbe00a4cc',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36',
    'content-type': 'application/json',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Referer': 'https://64.225.33.218.xip.io/c/local/projects-namespaces',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
}

params = (
    ('limit', '-1'),
    ('sort', 'name'),
)

# response = requests.get('https://64.225.33.218.xip.io/v3/projects', headers=headers, params=params, cookies=cookies, verify=False)

#NB. Original query string below. It seems impossible to parse and
#reproduce query strings 100% accurately so the one below is given
#in case the reproduced version is not "correct".
print(dir(client.rancher_api_client()))
"""
for i in range(10):
    start = time.time()
    response = requests.get('https://64.225.33.218.xip.io/v3/projects?limit=-1&sort=name', headers=headers, cookies=cookies, verify=False)
    response.text
    print("projects", time.time() - start)
"""
# projects = client.rancher_api_client().

