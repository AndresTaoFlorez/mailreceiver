

[ ] - actualizar nombre de la tabla mails por conversations

 psql -U mailreceiver -d mailreceiver -h localhost -c "
  ALTER TABLE conversations RENAME TO conversations;
  ALTER TABLE conversations RENAME CONSTRAINT uq_conversation_id TO
  uq_conv_id;
  "
[ ] - Averiguar si es posible hacer muchas peticiones rapidamente a la base de datos para ir inyectando informacion, o es mejor usar redis para esto y que cuando ya haya un buen paquete de data ahi si enviar a la base de datos y con ello reducir las llamadas diabolicas a la base de datos, y que cuando ya el proceso este terminado ya la informacion guardada completa en la base de datos entonces que el usuario ya no consulte directamente el redis si no en su lugar la base de datos que es mas rapida para responder que para inyectar:

# Implementar REDIS
1. Leer cien correos
2. Inyectar en REDIS cada dato obtenido sin esperar nada como si fuera la base de datos, y permitir consultar lo guardado inmediatamente, se puede entender como una barra de carga que se va llenando desde la perspectiva del usuario.
3. La base de datos debe contar con una table de configuracion que permitira guardar un campo para establecer la cantidad de datos que se deben retener en REDIS antes de enviar y hacer el insert en la base de datos de POSTGRESQL, es decir, si son 100 correos y ya el agente ha leido 28, y la configuracion tiene el numero 10, entonces cuando haya llegado a diez correos enviara esa informacion con los 10, en lugar de hacer una peticion por cada uno, y luego quedaran 8 pendientes (28 - 10), esperando a que se completen los otros 10, pero si el agente termina justo en ese momento entonces se deben enviar esos 8 porque asi quedaron. Al final del ciclo o flujo el redis debe quedar completamente vacio.
4. Permitir consultar los resultados ya guardados en la base de datos de postgresql

[ ] - El flujo deberia ser el siguiente.

Arranca el mailreceiver (RPA) segun el aplicativo seleccionado abriendo un navegador por aplicativo y navegando hacia la UR y espsera las peticiones desde la API sin cerrarse durante la sesion.
- El Agente estara constantemente observando si hay correos en las carpetas de level1 y level2, asi se le llama pero para reconocer estas carpetas al hacer scraping se puede configurar el nombre de como aparecen en Outlook desde el endpoint de folder-config de la seccion de endpoints del aplicativo correspondiente, por ejemplo para el level1 la carpeta en outlook puede llamarse 'SOPORTE BASICO', y para level2 puede llamarse 'SOPORTE AVANZADO'.
- Si observa que hay conversations dentro de las carpetas de level1 y leve2 entonces empezara a revisarlos uno a uno y a guardarlos en la base de datos (conversations).
- Cada vez que se obtenga un correo lo vas a guardar directamente en un REDIS que vas a levantar dedicado al mailreceiver, y cuando termine ese ciclo pasas lo que esta en REDIS a postgresql, y limpias el REDIS para tenerlo limpio y disponible de nuevo. La clave es que desde el front se estara leyendo con demasiada concurrencia, entonces para evitar hacer muchas peticiones a la base de datos, se hacen hacia REDIS, y cuando el ciclo termine apuntar no a REDIS sino a la base de datos, esto es solo mientras se estan obteniendo los correos, de modo que el usuario observe desde el front como se van cargando uno a uno los correos, el redis nos funcionaria como una especie de memoria ram de alta concurrencia mientras que guardan los datos de verdad.
- Una vez los correos (conversations) ya hayan sido guardados en postgresql, enviaras esa misma data al missaquest para crear los casos en el aplicativo correspondiente para obtener el numero de ticket de cada uno. Esto lo haras de forma paginadamente automatico para no enviar demasiadas solicitudes al missaquest.