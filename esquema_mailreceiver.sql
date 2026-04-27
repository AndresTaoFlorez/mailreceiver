--
-- PostgreSQL database dump
--

\restrict Yi4YNllZvKJsXANqqoSeuWahTmID8YXHGaBIcN48Gq97CHhmuVk3w2M967F2yLy

-- Dumped from database version 15.17 (Ubuntu 15.17-1.pgdg24.04+1)
-- Dumped by pg_dump version 15.17 (Ubuntu 15.17-1.pgdg24.04+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: conversations; Type: TABLE; Schema: public; Owner: mailreceiver
--

CREATE TABLE public.conversations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id character varying NOT NULL,
    app character varying(50) NOT NULL,
    folder character varying(200) NOT NULL,
    subject character varying DEFAULT ''::character varying NOT NULL,
    sender character varying DEFAULT ''::character varying NOT NULL,
    sender_email character varying DEFAULT ''::character varying NOT NULL,
    body text DEFAULT ''::text NOT NULL,
    tags text DEFAULT ''::text NOT NULL,
    to_address character varying DEFAULT ''::character varying NOT NULL,
    from_address character varying DEFAULT ''::character varying NOT NULL,
    year integer,
    month integer,
    day integer,
    hour integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.conversations OWNER TO mailreceiver;

--
-- Name: especialist; Type: TABLE; Schema: public; Owner: mailreceiver
--

CREATE TABLE public.especialist (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(20) NOT NULL,
    name character varying(200) NOT NULL,
    level integer NOT NULL,
    load_percentage integer,
    priority integer DEFAULT 0,
    active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.especialist OWNER TO mailreceiver;

--
-- Name: folder_config; Type: TABLE; Schema: public; Owner: mailreceiver
--

CREATE TABLE public.folder_config (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    folder_name character varying(200) NOT NULL,
    level integer NOT NULL,
    application character varying(50) NOT NULL,
    active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.folder_config OWNER TO mailreceiver;

--
-- Name: tickets; Type: TABLE; Schema: public; Owner: mailreceiver
--

CREATE TABLE public.tickets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(50),
    type character varying(100),
    application character varying(50) NOT NULL,
    conversation_id uuid,
    especialist_code character varying(20),
    date_time timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.tickets OWNER TO mailreceiver;

--
-- Name: conversations conversations_conversation_id_key; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_conversation_id_key UNIQUE (conversation_id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: especialist especialist_code_key; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.especialist
    ADD CONSTRAINT especialist_code_key UNIQUE (code);


--
-- Name: especialist especialist_pkey; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.especialist
    ADD CONSTRAINT especialist_pkey PRIMARY KEY (id);


--
-- Name: folder_config folder_config_folder_name_application_key; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.folder_config
    ADD CONSTRAINT folder_config_folder_name_application_key UNIQUE (folder_name, application);


--
-- Name: folder_config folder_config_pkey; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.folder_config
    ADD CONSTRAINT folder_config_pkey PRIMARY KEY (id);


--
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);


--
-- Name: conversations uq_conversation_id; Type: CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT uq_conversation_id UNIQUE (conversation_id);


--
-- Name: tickets tickets_especialist_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mailreceiver
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_especialist_code_fkey FOREIGN KEY (especialist_code) REFERENCES public.especialist(code);


--
-- PostgreSQL database dump complete
--

\unrestrict Yi4YNllZvKJsXANqqoSeuWahTmID8YXHGaBIcN48Gq97CHhmuVk3w2M967F2yLy

