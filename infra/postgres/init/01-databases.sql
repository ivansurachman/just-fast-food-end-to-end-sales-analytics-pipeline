-- Creates the Airflow, Metabase and analytics databases with one owner role each.
-- Passwords are read from the container environment, which compose fills from .env.
-- This file runs only on an empty data volume (Postgres image init behaviour).
\set ON_ERROR_STOP on

\getenv airflow_password POSTGRES_AIRFLOW_PASSWORD
\getenv metabase_password POSTGRES_METABASE_PASSWORD
\getenv analytics_password POSTGRES_ANALYTICS_PASSWORD

CREATE ROLE airflow LOGIN PASSWORD :'airflow_password';
CREATE ROLE metabase LOGIN PASSWORD :'metabase_password';
CREATE ROLE analytics LOGIN PASSWORD :'analytics_password';

CREATE DATABASE airflow OWNER airflow;
CREATE DATABASE metabase OWNER metabase;
CREATE DATABASE analytics OWNER analytics;
