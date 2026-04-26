

[ ] - actualizar nombre de la tabla mails por conversations

 psql -U mailreceiver -d mailreceiver -h localhost -c "
  ALTER TABLE conversations RENAME TO conversations;
  ALTER TABLE conversations RENAME CONSTRAINT uq_conversation_id TO
  uq_conv_id;
  "
[ ] - Averiguar si es posible hacer muchas peticiones rapidamente a la base de datos para ir inyectando informacion, o es mejor usar redis para esto y que cuando ya haya un buen paquete de data ahi si enviar a la base de datos y con ello reducir las llamadas diabolicas a la base de datos, y que cuando ya el proceso este terminado ya la informacion guardada completa en la base de datos entonces que el usuario ya no consulte directamente el redis si no en su lugar la base de datos que es mas rapida para responder que para inyectar:

1. Leer cien correos
2. Inyectar en REDIS cada dato obtenido sin esperar nada como si fuera la base de datos, y permitir consultar lo guardado inmediatamente, se puede entender como una barra de carga que se va llenando desde la perspectiva del usuario.
3. La base de datos debe contar con una table de configuracion que permitira guardar un campo para establecer la cantidad de datos que se deben retener en REDIS antes de enviar y hacer el insert en la base de datos de POSTGRESQL, es decir, si son 100 correos y ya el agente ha leido 28, y la configuracion tiene el numero 10, entonces cuando haya llegado a diez correos enviara esa informacion con los 10, en lugar de hacer una peticion por cada uno, y luego quedaran 8 pendientes (28 - 10), esperando a que se completen los otros 10, pero si el agente termina justo en ese momento entonces se deben enviar esos 8 porque asi quedaron. Al final del ciclo o flujo el redis debe quedar completamente vacio.
4. Permitir consultar los resultados ya guardados en la base de datos de postgresql