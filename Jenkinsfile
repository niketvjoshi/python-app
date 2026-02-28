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
    # Docker-in-Docker sidecar
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

    # Main build container (Client)
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

    parameters {
        string(name: 'IMAGE_TAG', defaultValue: '', description: 'Override image tag (leave empty to auto-generate)')
        booleanParam(name: 'SKIP_TESTS', defaultValue: false, description: 'Skip tests and linting')
        booleanParam(name: 'DRY_RUN', defaultValue: false, description: 'Build but do not push/deploy')
    }

    environment {
        AWS_REGION      = 'ap-south-1'
        AWS_ACCOUNT_ID  = '196549506578'
        ECR_REPO        = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/python-app"
        
        // Fixed Tag Logic
        SHORT_SHA       = "${env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : 'no-git'}"
        TAG             = "${params.IMAGE_TAG ?: "${env.BUILD_NUMBER}-${SHORT_SHA}"}"

        MANIFESTS_REPO  = 'https://github.com/YOUR_ORG/nodejs-app-manifests.git'
        MANIFESTS_BRANCH = 'main'
        HELM_CHART_PATH = 'helm/python-app'
        APP_NAME        = 'python-app'
    }

    options {
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    stages {
        stage('Initialize') {
            steps {
                container('tools') {
                    script {
                        echo "🚀 Starting Build for ${APP_NAME}"
                        echo "Image Tag: ${TAG}"
                    }
                }
            }
        }

        stage('Install Dependencies') {
            steps {
                container('tools') {
                    sh '''
                        apk add --no-cache aws-cli git curl wget gcc musl-dev python3-dev linux-headers
                        pip install --no-cache-dir -r app/requirements.txt
                    '''
                }
            }
        }

        stage('Tests & Quality') {
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
                stage('Linting') {
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
                        # Wait for DinD to be ready
                        MAX_RETRIES=30
                        COUNT=0
                        until docker info > /dev/null 2>&1 || [ $COUNT -eq $MAX_RETRIES ]; do
                            echo "Waiting for Docker daemon... ($COUNT/$MAX_RETRIES)"
                            sleep 2
                            COUNT=$((COUNT + 1))
                        done

                        docker build \
                            --build-arg APP_VERSION=${TAG} \
                            -t ${ECR_REPO}:${TAG} \
                            -t ${ECR_REPO}:latest .
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
                    '''
                }
            }
        }

        stage('Update GitOps Manifests') {
            when { 
                allOf { 
                    expression { !params.DRY_RUN }
                    branch 'main'
                }
            }
            steps {
                container('tools') {
                    withCredentials([usernamePassword(credentialsId: 'github-credentials', usernameVariable: 'GIT_USER', passwordVariable: 'GIT_TOKEN')]) {
                        sh '''
                            wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
                            chmod +x /usr/local/bin/yq

                            git clone https://${GIT_USER}:${GIT_TOKEN}@${MANIFESTS_REPO#https://} manifests
                            cd manifests
                            
                            git config user.email "jenkins@ci.local"
                            git config user.name "Jenkins CI"

                            yq e ".image.tag = \\"${TAG}\\"" -i ${HELM_CHART_PATH}/values.yaml
                            
                            git add .
                            git commit -m "chore: update ${APP_NAME} to ${TAG} [skip ci]"
                            git push origin ${MANIFESTS_BRANCH}
                        '''
                    }
                }
            }
        }

        stage('ArgoCD Sync & Verify') {
            when { 
                allOf { 
                    expression { !params.DRY_RUN }
                    branch 'main'
                }
            }
            steps {
                container('tools') {
                    sh '''
                        # Minimal verification loop
                        echo "Verifying ArgoCD deployment..."
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
                    echo "Cleanup failed: ${e.message}"
                }
            }
        }
    }
}