# Build on the deployment platform from an operator-staged image digest and bundle.
# The base supplies Python 3.12 plus a local C compiler; GnuCOBOL is optional.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS runtime
COPY bundle/ /opt/bundle/
RUN python /opt/bundle/offline.py verify --bundle /opt/bundle && \
    python /opt/bundle/offline.py install --bundle /opt/bundle --environment /opt/runtime
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PIP_NO_INDEX=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /tmp
USER 65532:65532
ENTRYPOINT ["/opt/runtime/bin/python", "/opt/bundle/offline.py", "serve", "--bundle", "/opt/bundle"]
CMD ["--corpus", "/corpus", "--copybook", "/copybooks"]
