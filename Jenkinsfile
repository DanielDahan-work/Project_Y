pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
    }

    environment {
        NAS_HOST = '10.50.2.10'
        NAS_USER = 'ubuntu'
        NAS_BACKUP_ROOT = '/data/share/project-y-builds'
        IMAGE_BUILT = 'false'
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    def checkoutInfo = checkout scm
                    env.GIT_COMMIT = checkoutInfo.GIT_COMMIT
                    env.BUILD_IMAGE = "project-y:build-${env.BUILD_NUMBER}-${env.GIT_COMMIT.take(12)}"
                }
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
                sh 'docker build -t "$BUILD_IMAGE" -t project-y:latest .'
                script { env.IMAGE_BUILT = 'true' }
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
                            --restart unless-stopped \
                            --name project-y \
                            -p 5000:5000 \
                            -e DB_HOST=10.50.2.10 \
                            -e DB_PORT=5432 \
                            -e DB_NAME=project_y \
                            -e DB_USER="$DB_USER" \
                            -e DB_PASSWORD="$DB_PASSWORD" \
                            -e AWS_REGION=us-east-1 \
                            "$BUILD_IMAGE"
                    '''
                }
            }
        }
    }

    post {
        always {
            script {
                if (fileExists('scripts/backup_build.py')) {
                    def resultBeforeBackup = currentBuild.currentResult
                    withCredentials([
                        file(credentialsId: 'project-y-nas-known-hosts', variable: 'NAS_KNOWN_HOSTS')
                    ]) {
                        sshagent(credentials: ['project-y-nas-backup']) {
                            withEnv(["BUILD_RESULT=${resultBeforeBackup}"]) {
                                sh 'python3 scripts/backup_build.py'
                            }
                        }
                    }
                } else {
                    error('NAS backup unavailable: checkout did not provide the backup script.')
                }
            }
        }
    }
}
