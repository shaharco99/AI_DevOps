pipeline {
    agent {
        docker {
            image 'python:3.11-slim'
            args '-u root'
        }
    }

    environment {
        PYTHON_VERSION = '3.11'
        DOCKER_REGISTRY = 'your-registry.com'
        IMAGE_NAME = 'ai-devops-assistant'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    python -m pip install --upgrade pip
                    pip install -r requirements.txt
                    pip install -e ".[dev]"
                '''
            }
        }

        stage('Lint and Static Analysis') {
            steps {
                sh '''
                    ruff check ai_devops_assistant tests
                    black --check ai_devops_assistant tests
                    mypy ai_devops_assistant
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    pytest tests/unit -v --cov=ai_devops_assistant \\
                        --cov-report=xml --cov-report=term-missing
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                    cobertura coberturaReportFile: 'coverage.xml'
                }
            }
        }

        stage('Security Scan') {
            steps {
                sh '''
                    pip install bandit pip-audit
                    bandit -r ai_devops_assistant -ll
                    pip-audit -r requirements.txt
                '''
            }
        }

        stage('Docker Build') {
            steps {
                script {
                    docker.build("${DOCKER_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}")
                }
            }
        }

        stage('Container Security Scan') {
            steps {
                sh """
                    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \\
                        aquasec/trivy:latest image --exit-code 1 --no-progress \\
                        --format json --output trivy-results.json \\
                        ${DOCKER_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}
                """
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    docker.withRegistry("https://${DOCKER_REGISTRY}", 'docker-registry-credentials') {
                        docker.image("${DOCKER_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}").push()
                        docker.image("${DOCKER_REGISTRY}/${IMAGE_NAME}:${BUILD_NUMBER}").push('latest')
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when {
                branch 'main'
            }
            steps {
                withKubeConfig([credentialsId: 'kubeconfig', serverUrl: 'https://your-k8s-cluster.com']) {
                    sh '''
                        kubectl apply -f infra/kubernetes/namespace.yaml
                        kubectl apply -f infra/kubernetes/
                        kubectl rollout status deployment/ai-devops-assistant -n ai-devops-assistant
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker system prune -f'
            cleanWs()
        }
        success {
            echo 'Pipeline succeeded!'
        }
        failure {
            echo 'Pipeline failed!'
        }
    }
}