FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL com.redhat.component="rhos-ls-mcps" \
      name="openstack-lightspeed/rhos-mcps" \
      summary="MCP server providing OpenStack tools for RHOS-Lightspeed" \
      io.k8s.name="rhos-mcps" \
      io.k8s.description="MCP Tools for RHOS-Lightspeed" \
      io.openshift.tags="openstack,lightspeed,mcp" \
      org.label-schema.vcs-url="https://github.com/openstack-lightspeed/rhos-mcps"

WORKDIR /app

RUN pip install --no-cache-dir pdm

COPY pyproject.toml pdm.lock README.md ./
COPY src/ src/

RUN pdm install --prod --no-editable --frozen-lockfile

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

USER 1001

ENTRYPOINT ["rhos-ls-mcps"]
