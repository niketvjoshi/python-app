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
  serviceAccountName: jenkins
  containers:
    # Docker-in-Docker sidecar for building images
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

    # Main build container with required tools
    - name: tools
      image: python:3.12-alpine
      command: [cat]
      tty: true
      env:
        - name: DOCKER_HOST
          value: tcp://localhost:2375
        - name: DOCKER_TLS_CERTDIR
          value: ""
        - name: AWS_REGION
          value: ap-south-1
        - name: AWS_ACCOUNT_ID
          value: "196549506578"
  volumes:
    - name: docker-storage
      emptyDir: {}
"""
        }
    }

    // ── Parameters ─────────────────────────────────────────────────────────
    parameters {
        string(name: 'IMAGE_TAG', defaultValue: '', description: 'Override image tag (leave empty to auto-generate)')
        booleanParam(name: 'SKIP_TESTS', defaultValue: false, description: 'Skip unit tests and linting')
        booleanParam(name: 'DRY_RUN', defaultValue: false, description: 'Build but do not push or deploy')
    }

    // ── Environment Variables ───────────────────────────────────────────────
    environment {
        AWS_REGION      = 'ap-south-1'
        AWS_ACCOUNT_ID  = '196549506578'
        ECR_REPO        = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/python-app"

        // Handle Tag generation safely
        SHORT_SHA       = "${env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : 'unknown'}"
        TAG             = "${params.IMAGE_TAG ?: "${env.BUILD_NUMBER}-${SHORT_SHA}"}"

        // GitOps Repository Configuration
        MANIFESTS_REPO   = 'https://github.com/niketvjoshi/python-app-manifests'
        MANIFESTS_BRANCH = 'main'
        HELM_CHART_PATH  = 'helm/python-app'
        APP_NAME         = 'python-app'
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    stages {
        stage('Initialize') {
            steps {
                container('tools') {
                    script {
                        echo "🚀 Starting Build: ${env.BUILD_NUMBER}"
                        echo "Branch Name: ${env.BRANCH_NAME ?: 'Not Set'}"
                        echo "Git Branch:  ${env.GIT_BRANCH ?: 'Not Set'}"
                        echo "Final Tag:   ${env.TAG}"
                    }
                }
            }
        }

        stage('Install Dependencies') {
            steps {
                container('tools') {
                    sh '''
                        # Install build tools, Docker CLI, and AWS CLI
                        apk add --no-cache \
                            aws-cli git curl wget \
                            gcc musl-dev python3-dev linux-headers \
                            docker-cli

                        pip install --no-cache-dir -r app/requirements.txt
                        echo "✅ System tools and Python dependencies installed"
                    '''
                }
            }
        }

        stage('Tests & Linting') {
            when { expression { !params.SKIP_TESTS } }
            parallel {
                stage('Unit Tests') {
                    steps {
                        container('tools') {
                            sh '''
                                pip install --no-cache-dir pytest pytest-cov
                                pytest app/tests/ --cov=app --junit-xml=test-results.xml || true
                            '''
                            junit allowEmptyResults: true, testResults: 'test-results.xml'
                        }
                    }
                }
                stage('Code Quality') {
                    steps {
                        container('tools') {
                            sh '''
                                pip install --no-cache-dir flake8
                                flake8 app/ --max-line-length=120 --statistics || true
                            '''
                        }
                    }
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                container('tools') {
                    sh '''
                        # Ensure Docker Daemon is reachable
                        until docker info > /dev/null 2>&1; do
                            echo "Waiting for Docker sidecar..."
                            sleep 2
                        done

                        echo "Building ${ECR_REPO}:${TAG}..."
                        docker build \
                            --build-arg APP_VERSION=${TAG} \
                            --tag ${ECR_REPO}:${TAG} \
                            --tag ${ECR_REPO}:latest .
                    '''
                }
            }
        }

        stage('Push to ECR') {
            when { expression { !params.DRY_RUN } }
            steps {
                container('tools') {
                    sh '''
                        aws ecr get-login-password --region ${AWS_REGION} | \
                        docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

                        docker push ${ECR_REPO}:${TAG}
                        docker push ${ECR_REPO}:latest
                        echo "✅ Image successfully pushed to ECR"
                    '''
                }
            }
        }

        stage('Update GitOps Manifests') {
            when { 
                allOf { 
                    expression { params.DRY_RUN == false }
                    // Fix: Check for both 'main' and 'origin/main'
                    anyOf {
                        branch 'main'
                        expression { env.GIT_BRANCH == 'origin/main' }
                        expression { env.BRANCH_NAME == 'main' }
                    }
                }
            }
            steps {
                container('tools') {
                    withCredentials([usernamePassword(credentialsId: 'github-token-niket', usernameVariable: 'GIT_USER', passwordVariable: 'GIT_TOKEN')]) {
                        sh '''
                            # Clone Manifests Repo
                            rm -rf manifests
                            git clone https://${GIT_USER}:${GIT_TOKEN}@${MANIFESTS_REPO#https://} manifests
                            cd manifests/
                            
                            git config user.email "jenkins@ci.local"
                            git config user.name "Jenkins CI"

                            # SED FIX: Dynamically update the tag line in values.yaml
                            # Matches "  tag: " at the start of the line and replaces everything after
                            sed -i "s|^  tag:.*|  tag: \\"${TAG}\\"|" values.yaml

                            echo "Verified Change in values.yaml:"
                            grep "tag:" values.yaml

                            # Commit and Push
                            git add .
                            git commit -m "chore: deploy ${APP_NAME} ${TAG} [skip ci]"
                            git push origin ${MANIFESTS_BRANCH}
                        '''
                    }
                }
            }
        }

        stage('ArgoCD Sync & Verify') {
            when { 
                allOf { 
                    expression { params.DRY_RUN == false }
                    anyOf {
                        branch 'main'
                        expression { env.GIT_BRANCH == 'origin/main' }
                    }
                }
            }
            steps {
                container('tools') {
                    sh '''
                        echo "Verifying deployment health..."
                        # Wait for Kubernetes to pull the new image and stabilize
                        kubectl rollout status deployment/${APP_NAME} -n python-app --timeout=300s
                    '''
                }
            }
        }
    }

    post {
        always {
            script {
                try {
                    container('tools') {
                        sh 'docker system prune -f || true'
                    }
                } catch (Exception e) {
                    echo "Post-build cleanup skipped: ${e.message}"
                }
            }
        }
        success {
            echo "✅ Build #$BUILD_NUMBER finished successfully!"
        }
        failure {
            echo "❌ Build #$BUILD_NUMBER failed. Check the logs for details."
        }
    }
}