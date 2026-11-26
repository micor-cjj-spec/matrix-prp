"""Deterministic promtool fixtures for original rule timings."""
import json


def tests(rules):
    by_name={r["alert"]:r for r in rules["groups"][0]["rules"]}
    labels=lambda job,instance,extra="":'{environment="synthetic",job="'+job+'",instance="'+instance+'"'+extra+'}'
    n=labels("node","fixture-node")
    disk=labels("node","fixture-node",',mountpoint="/"')
    cpu=labels("node","fixture-node",',cpu="0",mode="idle"')
    cpu_user=labels("node","fixture-node",',cpu="0",mode="user"')
    http=labels("http_health","fixture-http_health")
    https=labels("https_health","fixture-https_health")
    mysql=labels("p2-mysql","fixture-p2-mysql")
    nginx=labels("p2-nginx","fixture-p2-nginx")
    ci=labels("p2-ci","fixture-ci")
    fail=labels("p2-ci","fixture-ci",',state="failure"')
    app200=labels("p2-app","fixture-p2-app",',status="200"')
    app500=labels("p2-app","fixture-p2-app",',status="500"')

    def row(metric,tag,values):
        return {"series":metric+tag,"values":values}

    def case(series, expected, name, at="4m"):
        checks=[]
        for alert,r in by_name.items():
            expected_alerts=[]
            if alert in expected:
                for tags in expected[alert]:
                    expected_alerts.append({"exp_labels":{**tags,"severity":r["labels"]["severity"]},
                                            "exp_annotations":r["annotations"]})
            checks.append({"eval_time":at,"alertname":alert,"exp_alerts":expected_alerts})
        return {"name":name,"interval":"15s","input_series":series,"alert_rule_test":checks}

    def tag(job,instance,**kwargs):
        return {"environment":"synthetic","job":job,"instance":instance,**kwargs}

    def base(ci_fresh="1x16"):
        return [row("up",n,"1x16"),row("up",http,"1x16"),row("up",https,"1x16"),
                row("up",mysql,"1x16"),row("up",nginx,"1x16"),row("up",ci,"1x16"),
                row("prp_ci_projection_fresh",ci,ci_fresh)]

    node=tag("node","fixture-node")
    positive=base()+[
        row("node_cpu_seconds_total",cpu,"0+1x16"),row("node_cpu_seconds_total",cpu_user,"0+14x16"),
        row("node_memory_MemAvailable_bytes",n,"50x16"),row("node_memory_MemTotal_bytes",n,"1000x16"),
        row("node_filesystem_avail_bytes",disk,"100x16"),row("node_filesystem_size_bytes",disk,"1000x16"),
        row("probe_success",http,"0x16"),row("probe_success",https,"1x16"),
        row("probe_ssl_earliest_cert_expiry",https,"100000x16"),
        row("mysql_up",mysql,"0x16"),row("nginx_up",nginx,"0x16"),
        row("http_server_requests_seconds_count",app200,"0+120x16"),
        row("http_server_requests_seconds_count",app500,"0+30x16"),
        row("http_server_requests_seconds_sum",app200,"0+300x16"),
        row("prp_ci_run_state",fail,"1x16"),
    ]
    positives={
        "HostCPUHigh":[node],"HostMemoryLow":[node],"HostMemoryCritical":[node],
        "HostRootDiskLow":[{**node,"mountpoint":"/"}],"ProbeTargetDown":[tag("http_health","fixture-http_health")],
        "MySQLTargetDown":[tag("p2-mysql","fixture-p2-mysql")],
        "NginxTargetDown":[tag("p2-nginx","fixture-p2-nginx")],
        "TLSCertificateExpiring":[tag("https_health","fixture-https_health")],
        "ApplicationErrorRateHigh":[tag("p2-app","fixture-p2-app")],
        "ApplicationMeanLatencyHigh":[tag("p2-app","fixture-p2-app")],
        "CIExecutionFailed":[tag("p2-ci","fixture-ci",state="failure")],
    }
    healthy=base()+[row("node_cpu_seconds_total",cpu,"0+14x16"),row("node_cpu_seconds_total",cpu_user,"0+1x16"),
        row("node_memory_MemAvailable_bytes",n,"500x16"),row("node_memory_MemTotal_bytes",n,"1000x16"),
        row("node_filesystem_avail_bytes",disk,"500x16"),row("node_filesystem_size_bytes",disk,"1000x16"),
        row("probe_success",http,"1x16"),row("probe_success",https,"1x16"),
        row("probe_ssl_earliest_cert_expiry",https,"3000000x16"),row("mysql_up",mysql,"1x16"),
        row("nginx_up",nginx,"1x16"),row("http_server_requests_seconds_count",app200,"0+30x16"),
        row("http_server_requests_seconds_sum",app200,"0+2x16"),row("prp_ci_run_state",fail,"0x16")]
    scrape=base("0x16")
    scrape=[x for x in scrape if x["series"]!="up"+mysql]
    scrape += [row("up",mysql,"0x16"),row("mysql_up",mysql,"0x16"),row("prp_ci_run_state",fail,"1x16")]
    absent=[x for x in base() if not x["series"].startswith("prp_ci_projection_fresh")]
    sparse=base()+[row("http_server_requests_seconds_count",app500,"0+1x16"),
                   row("http_server_requests_seconds_sum",app500,"0+10x16")]
    return {"rule_files":["/fixture/rules.yml"],"evaluation_interval":"15s","tests":[
        case(positive,positives,"positive-all-supported"),
        case(healthy,{},"healthy"),
        case(scrape,{"TargetScrapeDown":[tag("p2-mysql","fixture-p2-mysql")],
                     "CIEvidenceUnavailable":[tag("p2-ci","fixture-ci")]},"scrape-and-stale-distinct"),
        case(absent,{"CIEvidenceUnavailable":[tag("p2-ci","fixture-ci")]},"absent-ci"),
        case(sparse,{},"low-request-volume"),
        case(positive,{},"hold-duration","0m"),
        case([],{},"before-first-scrape"),
        case(base()+[row("node_cpu_seconds_total",cpu,"0+13.5x16"),row("node_cpu_seconds_total",cpu_user,"0+1.5x16")],{},"short-window-healthy-cpu","30s"),
        case(base()+[row("node_cpu_seconds_total",cpu,"0x16"),row("node_cpu_seconds_total",cpu_user,"0x16")],{},"zero-cpu-counter-delta"),
        case([row("up",ci,"0x16")],{"TargetScrapeDown":[tag("p2-ci","fixture-ci")]},"ci-scrape-down-not-evidence-missing"),
    ]}
