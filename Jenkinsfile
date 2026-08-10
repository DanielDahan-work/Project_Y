pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh 'python3 -m venv venv'
                sh './venv/bin/pip install -r requirements.txt'
            }
        }

        stage('Validate Flask') {
            steps {
                sh './venv/bin/python -m py_compile run.py'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t project-y:latest .'
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    docker stop project-y || true
                    docker rm project-y || true

                    docker run -d \
                        --name project-y \
                        -p 5000:5000 \
                        project-y:latest
                '''
            }
        }
    }
}