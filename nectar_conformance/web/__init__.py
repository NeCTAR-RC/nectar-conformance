"""Read-only web dashboard for nectar-conformance.

The dashboard never touches PuppetDB. A scheduled refresh (the
``nectar-conformance-refresh`` command, run by a k8s CronJob) evaluates every site and
writes a JSON report per site to a shared directory; the FastAPI app here serves those
stored reports plus changelog/version views computed live from the packaged check data.
One deployment per tier.
"""
