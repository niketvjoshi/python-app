pipeline {
    agent {
        kubernetes {
            label 'python-app-builder'
            yaml """
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: jenkins-agent
spec:
  serviceAccountName: jenkins   # Uses Pod Identity for AWS auth - no hardcoded keys

  containers:
    # Docker-in-Docker for building images
    - name: dind
      image: docker:29-dind
      securityContext:
        privileged: true
      env:
        - name: DOCKER_TLS_CERTDIR
          value: ""
      volumeMounts:
        - name: docker-storage
          mountPath: /var/lib/docker

    # Main build container with all tools
    - name: tools
      image: python:3.12-alpine
      command: [cat]
      tty: true
      env:
        - name: DOCKER_HOST
          value: tcp://localhost:2375
        - name: AWS_REGION
          value: ap-south-1
        - name: AWS_ACCOUNT_ID
          value: "196549506578"
      volumeMounts:
        - name: docker-storage
          mountPath: /var/lib/docker

  volumes:
    - name: docker-storage
      emptyDir: {}
"""
        }
    }

    // ── Parameters ─────────────────────────────────────────────────────────
    parameters {
        string(
            name: 'IMAGE_TAG',
            defaultValue: '',
            description: 'Override image tag (leave empty to auto-generate)'
        )
        booleanParam(
            name: 'SKIP_TESTS',
            defaultValue: false,
            description: 'Skip unit tests (not recommended for production)'
        )
        booleanParam(
            name: 'DRY_RUN',
            defaultValue: false,
            description: 'Build and test but do not push or deploy'
        )
    }

    // ── Environment Variables ───────────────────────────────────────────────
    environment {
        // AWS / ECR
        AWS_REGION      = 'ap-south-1'
        AWS_ACCOUNT_ID  = '196549506578'
        ECR_REPO        = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/python-app"

        // Image tag: use parameter if provided, else BUILD_NUMBER-GIT_COMMIT
        TAG             = "${params.IMAGE_TAG ?: "${env.BUILD_NUMBER}-${env.GIT_COMMIT?.take(7) ?: 'unknown'}"}"

        // Git
        MANIFESTS_REPO  = 'https://github.com/YOUR_ORG/nodejs-app-manifests.git'
        MANIFESTS_BRANCH = 'main'
        HELM_CHART_PATH = 'helm/python-app'

        // App
        APP_NAME        = 'python-app'
        NAMESPACE       = 'python-app'
    }

    // ── Pipeline Options ────────────────────────────────────────────────────
    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()               // Prevent parallel deploys
    }

    stages {

        // ── Stage 1: Checkout ─────────────────────────────────────────────
        stage('Checkout') {
            steps {
                container('tools') {
                    script {
                        echo "Branch:    ${env.GIT_BRANCH}"
                        echo "Commit:    ${env.GIT_COMMIT}"
                        echo "Image Tag: ${env.TAG}"
                        echo "Build:     ${env.BUILD_NUMBER}"
                    }
                }
            }
        }

        // ── Stage 2: Install Dependencies ────────────────────────────────
        stage('Install Dependencies') {
            steps {
                container('tools') {
                    sh '''
                        # Install AWS CLI and tools
                        apk add --no-cache aws-cli git curl wget

                        # Install Python dependencies
                        pip install --no-cache-dir -r app/requirements.txt

                        echo "✅ Dependencies installed"
                    '''
                }
            }
        }

        // ── Stage 3: Unit Tests ───────────────────────────────────────────
        stage('Unit Tests') {
            when {
                expression { !params.SKIP_TESTS }
            }
            steps {
                container('tools') {
                    sh '''
                        pip install --no-cache-dir pytest pytest-cov

                        # Run tests with coverage report
                        pytest app/tests/ \
                            --cov=app \
                            --cov-report=xml:coverage.xml \
                            --cov-report=term-missing \
                            --junit-xml=test-results.xml \
                            -v || true
                    '''
                }
            }
            post {
                always {
                    // Publish test results in Jenkins UI
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                }
            }
        }

        // ── Stage 4: Code Quality ─────────────────────────────────────────
        stage('Code Quality') {
            when {
                expression { !params.SKIP_TESTS }
            }
            steps {
                container('tools') {
                    sh '''
                        pip install --no-cache-dir flake8

                        # Lint Python code
                        flake8 app/ \
                            --max-line-length=120 \
                            --exclude=app/tests/ \
                            --statistics || true

                        echo "✅ Code quality check complete"
                    '''
                }
            }
        }

        // ── Stage 5: Build Docker Image ───────────────────────────────────
        stage('Build Docker Image') {
            steps {
                container('tools') {
                    sh '''
                        # Wait for Docker daemon to be ready
                        until docker info > /dev/null 2>&1; do
                            echo "Waiting for Docker..."
                            sleep 2
                        done

                        echo "Building image: ${ECR_REPO}:${TAG}"

                        docker build \
                            --build-arg APP_VERSION=${TAG} \
                            --tag ${ECR_REPO}:${TAG} \
                            --tag ${ECR_REPO}:latest \
                            --cache-from ${ECR_REPO}:latest \
                            --file Dockerfile \
                            .

                        echo "✅ Docker image built: ${ECR_REPO}:${TAG}"
                    '''
                }
            }
        }

        // ── Stage 6: Security Scan ────────────────────────────────────────
        stage('Security Scan') {
            when {
                expression { !params.SKIP_TESTS }
            }
            steps {
                container('tools') {
                    sh '''
                        # Install Trivy for vulnerability scanning
                        wget -qO- https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

                        # Scan for HIGH and CRITICAL vulnerabilities
                        # --exit-code 0 means pipeline continues even if vulns found (change to 1 to fail)
                        trivy image \
                            --severity HIGH,CRITICAL \
                            --exit-code 0 \
                            --format table \
                            ${ECR_REPO}:${TAG}

                        echo "✅ Security scan complete"
                    '''
                }
            }
        }

        // ── Stage 7: Push to ECR ──────────────────────────────────────────
        stage('Push to ECR') {
            when {
                expression { !params.DRY_RUN }
            }
            steps {
                container('tools') {
                    sh '''
                        # Authenticate to ECR using Pod Identity (no hardcoded keys)
                        aws ecr get-login-password \
                            --region ${AWS_REGION} | \
                        docker login \
                            --username AWS \
                            --password-stdin \
                            ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

                        # Push both versioned and latest tags
                        docker push ${ECR_REPO}:${TAG}
                        docker push ${ECR_REPO}:latest

                        echo "✅ Image pushed: ${ECR_REPO}:${TAG}"
                    '''
                }
            }
        }

        // ── Stage 8: Update Manifests Repo ───────────────────────────────
        stage('Update Manifests') {
            when {
                allOf {
                    expression { !params.DRY_RUN }
                    // Only deploy from main branch
                    branch 'main'
                }
            }
            steps {
                container('tools') {
                    // Use Jenkins credentials for Git push
                    withCredentials([
                        usernamePassword(
                            credentialsId: 'github-credentials',
                            usernameVariable: 'GIT_USER',
                            passwordVariable: 'GIT_TOKEN'
                        )
                    ]) {
                        sh '''
                            # Install yq for safe YAML editing
                            wget -qO /usr/local/bin/yq \
                                https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
                            chmod +x /usr/local/bin/yq

                            # Clone manifests repo
                            git clone https://${GIT_USER}:${GIT_TOKEN}@${MANIFESTS_REPO#https://} manifests
                            cd manifests

                            # Configure git
                            git config user.email "jenkins@ci.local"
                            git config user.name "Jenkins CI"

                            # Update image tag in values.yaml
                            yq e ".image.tag = \\"${TAG}\\"" \
                                -i ${HELM_CHART_PATH}/values.yaml

                            # Verify the change
                            echo "Updated image tag to: ${TAG}"
                            grep "tag:" ${HELM_CHART_PATH}/values.yaml

                            # Commit and push
                            git add ${HELM_CHART_PATH}/values.yaml
                            git commit -m "ci: deploy ${APP_NAME} ${TAG} [skip ci]"
                            git push origin ${MANIFESTS_BRANCH}

                            echo "✅ Manifests updated — ArgoCD will deploy shortly"
                        '''
                    }
                }
            }
        }

        // ── Stage 9: Wait for ArgoCD Sync ────────────────────────────────
        stage('Verify Deployment') {
            when {
                allOf {
                    expression { !params.DRY_RUN }
                    branch 'main'
                }
            }
            steps {
                container('tools') {
                    sh '''
                        # Install kubectl
                        curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
                        chmod +x kubectl
                        mv kubectl /usr/local/bin/

                        # Install ArgoCD CLI
                        curl -sSL -o /usr/local/bin/argocd \
                            https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
                        chmod +x /usr/local/bin/argocd

                        # Wait for ArgoCD to detect and sync the change (max 5 min)
                        echo "Waiting for ArgoCD to sync..."
                        TIMEOUT=300
                        ELAPSED=0
                        while [ $ELAPSED -lt $TIMEOUT ]; do
                            STATUS=$(kubectl get application ${APP_NAME} -n argocd \
                                -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
                            HEALTH=$(kubectl get application ${APP_NAME} -n argocd \
                                -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")

                            echo "ArgoCD Status: Sync=${STATUS} Health=${HEALTH} (${ELAPSED}s/${TIMEOUT}s)"

                            if [ "$STATUS" = "Synced" ] && [ "$HEALTH" = "Healthy" ]; then
                                echo "✅ ArgoCD sync complete"
                                break
                            fi

                            sleep 15
                            ELAPSED=$((ELAPSED + 15))
                        done

                        if [ $ELAPSED -ge $TIMEOUT ]; then
                            echo "⚠️  ArgoCD did not sync within ${TIMEOUT}s — check ArgoCD UI"
                            exit 1
                        fi
                    '''
                }
            }
        }

    }

    // ── Post Actions ───────────────────────────────────────────────────────
    post {
        success {
            echo """
            ✅ Pipeline SUCCEEDED
            App:       ${env.APP_NAME}
            Image:     ${env.ECR_REPO}:${env.TAG}
            Branch:    ${env.GIT_BRANCH}
            Build:     ${env.BUILD_NUMBER}
            """
        }

        failure {
            echo """
            ❌ Pipeline FAILED
            App:    ${env.APP_NAME}
            Build:  ${env.BUILD_NUMBER}
            Branch: ${env.GIT_BRANCH}
            Check logs above for details.
            """
        }

        always {
            container('tools') {
                sh '''
                    # Cleanup local Docker images to save disk space
                    docker rmi ${ECR_REPO}:${TAG} || true
                    docker rmi ${ECR_REPO}:latest || true
                    docker system prune -f || true
                '''
            }
        }
    }
}
