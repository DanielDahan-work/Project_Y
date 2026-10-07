def imageBuilt = false

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
                sh './venv/bin/python -m unittest discover -s tests -v'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t "$BUILD_IMAGE" -t project-y:latest .'
                script { imageBuilt = true }
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'project-y-db',
                        usernameVariable: 'DB_USER',
                        passwordVariable: 'DB_PASSWORD'
                    ),
                    string(credentialsId: 'project-y-brevo-api-key', variable: 'BREVO_API_KEY'),
                    string(credentialsId: 'project-y-secret-key', variable: 'SECRET_KEY')
                ]) {
                    sh '''
                        set -eu
                        set +x
                        test -n "$BREVO_API_KEY"
                        test "${#SECRET_KEY}" -ge 32
                        export DB_HOST=10.50.2.10 DB_PORT=5432 DB_NAME=project_y
                        export EMAIL_SENDER=noreply@project-x.ink
                        export PUBLIC_BASE_URL=https://project-y.project-x.ink
                        export SESSION_COOKIE_SECURE=true

                        # Migrate before stopping the running site. A migration failure
                        # leaves the old container running; old code ignores added columns.
                        docker run --rm \
                            -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
                            "$BUILD_IMAGE" flask --app run migrate-email-verification

                        docker stop project-y || true
                        docker rm project-y || true

                        docker run -d \
                            --restart unless-stopped \
                            --name project-y \
                            -p 5000:5000 \
                            -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
                            -e BREVO_API_KEY -e SECRET_KEY \
                            -e EMAIL_SENDER -e PUBLIC_BASE_URL -e SESSION_COOKIE_SECURE \
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
                            withEnv(["BUILD_RESULT=${resultBeforeBackup}", "IMAGE_BUILT=${imageBuilt}"]) {
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
