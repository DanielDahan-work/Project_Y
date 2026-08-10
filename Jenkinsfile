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
        withCredentials([
            usernamePassword(
                credentialsId: 'project-y-db',
                usernameVariable: 'DB_USER',
                passwordVariable: 'DB_PASSWORD'
            )
        ]) {
            sh '''
                docker stop project-y || true
                docker rm project-y || true

                docker run -d \
                    --name project-y \
                    -p 5000:5000 \
                    -e DB_HOST=10.50.2.10 \
                    -e DB_PORT=5432 \
                    -e DB_NAME=project_y \
                    -e DB_USER="$DB_USER" \
                    -e DB_PASSWORD="$DB_PASSWORD" \
                    project-y:latest
            '''
        }
    }
}
    }
}