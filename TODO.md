

[ ] - actualizar nombre de la tabla mails por conversations

 psql -U mailreceiver -d mailreceiver -h localhost -c "
  ALTER TABLE conversations RENAME TO conversations;
  ALTER TABLE conversations RENAME CONSTRAINT uq_conversation_id TO
  uq_conv_id;
  "
