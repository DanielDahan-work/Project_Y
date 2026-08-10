pipeline {
    agent any

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
                sh 'find . -maxdepth 3 -type f'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t project-y:latest .'
            }
        }

    }
}