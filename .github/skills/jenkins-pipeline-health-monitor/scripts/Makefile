.PHONY: build-docker push-docker login clean test docker

DOCKER_REGISTRY ?= ger-is-registry.caas.intel.com
IMAGE_SERVER ?= $(DOCKER_REGISTRY)/fw-common/snic-images/jenkins_sanity_agent

BUILD_DATE = $(shell date -u -Idate)
COMMIT_SHA = $(shell git rev-parse --short=8 HEAD)
DOCKER_TAG = $(BUILD_DATE)_$(COMMIT_SHA)
DOCKER_IMAGE ?= $(IMAGE_SERVER):$(DOCKER_TAG)
LATEST_IMAGE ?= $(IMAGE_SERVER):latest

$(info == Building Jenkins Sanity Agent with the following configuration:)
$(info DOCKER_REGISTRY:  $(DOCKER_REGISTRY))
$(info IMAGE_SERVER:     $(IMAGE_SERVER))
$(info BUILD_DATE:       $(BUILD_DATE))
$(info COMMIT_SHA:       $(COMMIT_SHA))
$(info DOCKER_TAG:       $(DOCKER_TAG))
$(info DOCKER_IMAGE:     $(DOCKER_IMAGE))
$(info LATEST_IMAGE:     $(LATEST_IMAGE))

login:
	@echo "Logging into Docker registry..."
	docker login $(DOCKER_REGISTRY)

build-docker: Dockerfile
	@echo "Building Jenkins Sanity Agent Docker image..."
	docker build -f Dockerfile --pull -t $(DOCKER_IMAGE) \
		--build-arg HTTP_PROXY=$(http_proxy) \
		--build-arg http_proxy=$(http_proxy) \
		--build-arg HTTPS_PROXY=$(http_proxy) \
		--build-arg https_proxy=$(http_proxy) \
		--label "build.date=$(BUILD_DATE)" \
		--label "build.commit=$(COMMIT_SHA)" \
		--label "build.version=$(DOCKER_TAG)" ../..
	@echo "Tagging as latest..."
	docker tag $(DOCKER_IMAGE) $(LATEST_IMAGE)

push-docker: build-docker
	@echo "Pushing Jenkins Sanity Agent to registry..."
	docker push $(DOCKER_IMAGE)
	docker push $(LATEST_IMAGE)
	@echo "Successfully pushed:"
	@echo "  - $(DOCKER_IMAGE)"
	@echo "  - $(LATEST_IMAGE)"

pull-docker:
	@echo "Pulling Jenkins Sanity Agent from registry..."
	docker pull $(LATEST_IMAGE)

run-local: build-docker
	@echo "Running Jenkins Sanity Agent locally..."
	docker run -d --name jenkins-sanity-agent-local \
		-p 8002:8002 \
		-e JENKINS_USERNAME=$(JENKINS_USERNAME) \
		-e JENKINS_API_TOKEN=$(JENKINS_API_TOKEN) \
		-e DB_FERNET_KEY=$(DB_FERNET_KEY) \
		-e JENKINS_PIPELINE_URL=$(JENKINS_PIPELINE_URL) \
		$(DOCKER_IMAGE)
	@echo "Container started. Access metrics at: http://localhost:8002/metrics"

stop-local:
	@echo "Stopping local Jenkins Sanity Agent..."
	-docker stop jenkins-sanity-agent-local
	-docker rm jenkins-sanity-agent-local

logs-local:
	@echo "Showing logs from local Jenkins Sanity Agent..."
	docker logs -f jenkins-sanity-agent-local

clean:
	@echo "Cleaning up Jenkins Sanity Agent Docker images..."
	-docker rmi -f $(shell docker images -f=reference="$(IMAGE_SERVER)" -q)
	-docker rmi -f $(shell docker images -f=reference="jenkins-pipeline-monitor" -q)

delete-docker:
	@echo "Deleting specific Jenkins Sanity Agent image..."
	-docker rmi -f $(shell docker images -f=reference="$(DOCKER_IMAGE)" -q)

# Convenience targets
docker: build-docker

all: login build-docker push-docker

# Development targets
dev-build: 
	@echo "Building development version..."
	docker build -t jenkins-sanity-agent:dev .

dev-run: dev-build
	@echo "Running development version..."
	docker run -it --rm \
		-p 8002:8002 \
		-e JENKINS_USERNAME=$(JENKINS_USERNAME) \
		-e JENKINS_API_TOKEN=$(JENKINS_API_TOKEN) \
		jenkins-sanity-agent:dev

# Help target
help:
	@echo "Jenkins Sanity Agent - Docker Build System"
	@echo "========================================="
	@echo ""
	@echo "Main targets:"
	@echo "  build-docker    - Build the Docker image"
	@echo "  push-docker     - Build and push to registry"
	@echo "  pull-docker     - Pull latest from registry"
	@echo "  login          - Login to Docker registry"
	@echo ""
	@echo "Local development:"
	@echo "  run-local      - Run container locally"
	@echo "  stop-local     - Stop local container"
	@echo "  logs-local     - View local container logs"
	@echo "  dev-build      - Build development version"
	@echo "  dev-run        - Run development version interactively"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          - Remove all Jenkins Sanity Agent images"
	@echo "  delete-docker  - Remove specific tagged image"
	@echo ""
	@echo "Environment variables:"
	@echo "  JENKINS_USERNAME    - Your Jenkins username"
	@echo "  JENKINS_API_TOKEN   - Your Jenkins API token"
	@echo "  http_proxy          - HTTP proxy for build (if needed)"
	@echo ""
	@echo "Examples:"
	@echo "  make build-docker"
	@echo "  make push-docker"
	@echo "  make run-local JENKINS_USERNAME=myuser JENKINS_API_TOKEN=mytoken"